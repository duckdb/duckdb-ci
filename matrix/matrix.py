from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OUTPUT_PLATFORMS = ("linux", "macos", "windows", "wasm")
PLATFORM_CONFIG_KEYS = {
    "linux": "linux",
    "macos": "osx",
    "windows": "windows",
    "wasm": "wasm",
}

PULL_REQUEST = "pull_request"
PUSH = "push"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExtensionGroup:
    artifact_prefix: str
    extra_toolchains: str
    default_exclude_archs: str
    opt_in_archs: str | None
    config_paths: tuple[str, ...]


EXTENSION_GROUPS = (
    ExtensionGroup(
        artifact_prefix="main-extensions",
        extra_toolchains="unixodbc;parser_tools",
        default_exclude_archs="",
        opt_in_archs=None,
        config_paths=(
            ".github/config/in_tree_extensions.cmake",
            ".github/config/out_of_tree_extensions.cmake",
        ),
    ),
    ExtensionGroup(
        artifact_prefix="rust-based-extensions",
        extra_toolchains="rust",
        default_exclude_archs="wasm_mvp;wasm_eh;wasm_threads;windows_amd64_rtools;windows_amd64_mingw;linux_amd64_musl",
        opt_in_archs="",
        config_paths=(".github/config/rust_based_extensions.cmake",),
    ),
    ExtensionGroup(
        artifact_prefix="external-extensions",
        extra_toolchains="rust",
        default_exclude_archs="wasm_mvp;wasm_eh;wasm_threads;windows_amd64_mingw;windows_amd64;linux_amd64_musl",
        opt_in_archs="",
        config_paths=(".github/config/external_extensions.cmake",),
    ),
)


class MatrixError(ValueError):
    pass


def split_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    values: list[str] = []
    seen: set[str] = set()
    for part in raw.replace(",", ";").split(";"):
        value = part.strip()
        if not value or value in seen:
            continue
        values.append(value)
        seen.add(value)
    return values


def join_list(values: list[str]) -> str:
    return ";".join(values)


def combine_lists(*raw_values: str | None) -> str:
    combined: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for value in split_list(raw):
            if value in seen:
                continue
            combined.append(value)
            seen.add(value)
    return join_list(combined)


def detect_event_type_from_env(env: dict[str, str] | None = None) -> str:
    env = env or os.environ
    event_path = env.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        return UNKNOWN
    return detect_event_type_from_file(Path(event_path))


def detect_event_type_from_file(path: Path) -> str:
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        return UNKNOWN
    if PULL_REQUEST in payload:
        return PULL_REQUEST
    if "ref" in payload:
        return PUSH
    return UNKNOWN


def resolve_reduced_ci_mode(mode: str | None, event_type: str) -> bool:
    mode = (mode or "auto").strip() or "auto"
    if mode not in {"auto", "enabled", "disabled"}:
        raise MatrixError(f"invalid reduced_ci_mode: {mode!r} (must be auto|enabled|disabled)")
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    return event_type == PULL_REQUEST


def load_extensions_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise MatrixError("extensions matrix must be a JSON object")
    for platform, config in data.items():
        if not isinstance(config, dict):
            raise MatrixError(f"platform {platform!r} must be an object")
        unknown_config_fields = set(config) - {"include"}
        if unknown_config_fields:
            fields = ", ".join(sorted(unknown_config_fields))
            raise MatrixError(f"platform {platform!r} has unknown fields: {fields}")
        include = config.get("include")
        if not isinstance(include, list):
            raise MatrixError(f"platform {platform!r} must have an include list")
        for entry in include:
            validate_entry(platform, entry)
    return data


def validate_entry(platform: str, entry: Any) -> None:
    if not isinstance(entry, dict):
        raise MatrixError(f"platform {platform!r} include entries must be objects")
    required = {
        "duckdb_arch",
        "runner",
        "vcpkg_target_triplet",
        "vcpkg_host_triplet",
        "run_in_reduced_ci_mode",
        "opt_in",
    }
    allowed = required | {"osx_build_arch"}
    unknown = set(entry) - allowed
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise MatrixError(f"entry {entry.get('duckdb_arch', '<unknown>')!r} has unknown fields: {fields}")
    missing = required - set(entry)
    if missing:
        fields = ", ".join(sorted(missing))
        raise MatrixError(f"entry {entry.get('duckdb_arch', '<unknown>')!r} is missing fields: {fields}")
    if not str(entry["duckdb_arch"]).strip():
        raise MatrixError("entry duckdb_arch cannot be empty")
    if not str(entry["runner"]).strip():
        raise MatrixError(f"entry {entry['duckdb_arch']!r} runner cannot be empty")


def parse_runners(raw: str | None) -> dict[str, list[str]]:
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MatrixError(f"parse runners: {exc}") from exc
    if not isinstance(data, dict):
        raise MatrixError("runners must be a JSON object")
    result: dict[str, list[str]] = {}
    for key, value in data.items():
        clean_key = str(key).strip()
        if not clean_key:
            raise MatrixError("runner override key cannot be empty")
        if isinstance(value, str):
            labels = [value]
        elif isinstance(value, list) and all(isinstance(label, str) for label in value):
            labels = value
        else:
            raise MatrixError(f"runner override for {clean_key!r} must be a string or string array")
        labels = [label.strip() for label in labels if label.strip()]
        if not labels:
            raise MatrixError(f"runner override for {clean_key!r} cannot be empty")
        result[clean_key] = labels
    return result


def runner_alias(duckdb_arch: str) -> str | None:
    if duckdb_arch in {"linux_amd64", "linux_amd64_musl"}:
        return "linux_x64"
    if duckdb_arch in {"linux_arm64", "linux_arm64_musl"}:
        return "linux_arm64"
    if duckdb_arch == "osx_amd64":
        return "macos_x64"
    if duckdb_arch == "osx_arm64":
        return "macos_arm64"
    if duckdb_arch in {"windows_amd64", "windows_amd64_mingw"}:
        return "windows_x64"
    if duckdb_arch == "windows_arm64":
        return "windows_arm64"
    if duckdb_arch in {"wasm_mvp", "wasm_eh", "wasm_threads"}:
        return "linux_x64"
    return None


def resolve_runner(entry: dict[str, Any], overrides: dict[str, list[str]]) -> list[str]:
    duckdb_arch = entry["duckdb_arch"]
    labels = overrides.get(duckdb_arch)
    if labels is None:
        alias = runner_alias(duckdb_arch)
        labels = overrides.get(alias or "")
    if labels is not None:
        return labels
    return [entry["runner"]]


def load_group_config(group: ExtensionGroup, root: Path) -> str:
    parts: list[str] = []
    for relative_path in group.config_paths:
        path = root / relative_path
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").rstrip("\n"))
    return "\n\n".join(part for part in parts if part)


def include_entry(entry: dict[str, Any], excluded: set[str], opt_in: set[str], reduced_ci: bool) -> bool:
    duckdb_arch = entry["duckdb_arch"]
    if duckdb_arch in excluded:
        return False
    if reduced_ci and not entry["run_in_reduced_ci_mode"]:
        return False
    if entry["opt_in"] and duckdb_arch not in opt_in:
        return False
    return True


def linux_container_name(duckdb_arch: str, artifact_prefix: str) -> str:
    if duckdb_arch.startswith("linux_amd64"):
        host_arch = "amd64"
    elif duckdb_arch.startswith("linux_arm64"):
        host_arch = "aarch64"
    else:
        raise MatrixError(f"unsupported Linux duckdb_arch for container: {duckdb_arch}")

    base_image = "alpine_3_22" if duckdb_arch.endswith("_musl") else "manylinux_2_28"
    toolchain = "main" if artifact_prefix == "main-extensions" else "rust"
    return f"{base_image}_{host_arch}_{toolchain}"


def build_job(
    entry: dict[str, Any],
    group: ExtensionGroup,
    runner: list[str],
    effective_exclude_archs: str,
    effective_opt_in_archs: str,
    extension_config: str,
    image_version: str,
    image_suffix: str,
    repository_owner: str,
) -> dict[str, Any]:
    job: dict[str, Any] = {
        "runner": runner,
        "vcpkg_target_triplet": entry["vcpkg_target_triplet"],
        "vcpkg_host_triplet": entry["vcpkg_host_triplet"],
        "duckdb_arch": entry["duckdb_arch"],
        "artifact_prefix": group.artifact_prefix,
        "exclude_archs": effective_exclude_archs,
        "opt_in_archs": effective_opt_in_archs,
        "extra_toolchains": group.extra_toolchains,
        "extension_config": extension_config,
    }
    if "osx_build_arch" in entry:
        job["osx_build_arch"] = entry["osx_build_arch"]
    if entry["duckdb_arch"].startswith("linux_"):
        container_name = linux_container_name(entry["duckdb_arch"], group.artifact_prefix)
        container_name_with_suffix = f"{container_name}{image_suffix}"
        job["container_name"] = container_name_with_suffix
        if image_version:
            job["container"] = f"ghcr.io/{repository_owner}/duckdb-ci/{container_name_with_suffix}:{image_version}"
    return job


def compute_matrices(
    extensions: dict[str, Any],
    *,
    exclude_archs: str = "",
    opt_in_archs: str = "",
    runners: str = "{}",
    reduced_ci_mode: str = "auto",
    event_type: str = UNKNOWN,
    image_version: str = "",
    image_suffix: str = "",
    repository_owner: str = "duckdb",
    config_root: Path | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    reduced_ci = resolve_reduced_ci_mode(reduced_ci_mode, event_type)
    runner_overrides = parse_runners(runners)
    config_root = config_root or Path.cwd()

    result: dict[str, dict[str, list[dict[str, Any]]]] = {
        output_platform: {"include": []} for output_platform in OUTPUT_PLATFORMS
    }
    for output_platform, config_key in PLATFORM_CONFIG_KEYS.items():
        if config_key not in extensions:
            raise MatrixError(f"missing platform in extensions.json: {config_key}")
        entries = extensions[config_key]["include"]
        for group in EXTENSION_GROUPS:
            effective_exclude_archs = combine_lists(group.default_exclude_archs, exclude_archs)
            effective_opt_in_archs = opt_in_archs if group.opt_in_archs is None else group.opt_in_archs
            excluded = set(split_list(effective_exclude_archs))
            opt_in = set(split_list(effective_opt_in_archs))
            extension_config = load_group_config(group, config_root)
            for entry in entries:
                if not include_entry(entry, excluded, opt_in, reduced_ci):
                    continue
                result[output_platform]["include"].append(
                    build_job(
                        entry,
                        group,
                        resolve_runner(entry, runner_overrides),
                        effective_exclude_archs,
                        effective_opt_in_archs,
                        extension_config,
                        image_version,
                        image_suffix,
                        repository_owner,
                    )
                )
        result[output_platform]["include"].sort(
            key=lambda job: (job["duckdb_arch"], job["artifact_prefix"])
        )
    return result


def render_github_output(matrices: dict[str, dict[str, list[dict[str, Any]]]]) -> str:
    lines = []
    for key in OUTPUT_PLATFORMS:
        payload = json.dumps(matrices[key], separators=(",", ":"), sort_keys=True)
        lines.append(f"{key}={payload}")
    return "\n".join(lines) + "\n"


def write_github_output(output_path: Path, matrices: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    with output_path.open("a", encoding="utf-8") as f:
        f.write(render_github_output(matrices))
