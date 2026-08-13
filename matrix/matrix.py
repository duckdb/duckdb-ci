from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar


Platform = Literal["linux", "macos", "windows", "wasm"]
OUTPUT_PLATFORMS: tuple[Platform, ...] = ("linux", "macos", "windows", "wasm")
PLATFORM_CONFIG_KEYS: dict[Platform, str] = {
    "linux": "linux",
    "macos": "osx",
    "windows": "windows",
    "wasm": "wasm",
}

PULL_REQUEST = "pull_request"
PUSH = "push"
UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ExtensionGroup:
    key: str
    toolchain: str
    default_exclude_archs: str
    opt_in_archs: str | None
    config_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuildJob:
    runner: list[str]
    vcpkg_target_triplet: str
    vcpkg_host_triplet: str
    duckdb_arch: str
    prefix: str
    artifact_name: str
    exclude_archs: str
    opt_in_archs: str
    extension_config: str
    osx_build_arch: str | None = None
    container_name: str | None = None
    container: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "runner": self.runner,
            "vcpkg_target_triplet": self.vcpkg_target_triplet,
            "vcpkg_host_triplet": self.vcpkg_host_triplet,
            "duckdb_arch": self.duckdb_arch,
            "artifact_prefix": self.prefix,
            "artifact_name": self.artifact_name,
            "exclude_archs": self.exclude_archs,
            "opt_in_archs": self.opt_in_archs,
            "extension_config": self.extension_config,
        }
        if self.osx_build_arch is not None:
            result["osx_build_arch"] = self.osx_build_arch
        if self.container_name is not None:
            result["container_name"] = self.container_name
        if self.container is not None:
            result["container"] = self.container
        return result


@dataclass(frozen=True, slots=True)
class TestJob:
    runner: list[str]
    duckdb_arch: str
    artifact_pattern: str
    osx_build_arch: str | None = None
    container_name: str | None = None
    container: str | None = None

    @property
    def prefix(self) -> None:
        return None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "runner": self.runner,
            "duckdb_arch": self.duckdb_arch,
            "artifact_pattern": self.artifact_pattern,
        }
        if self.osx_build_arch is not None:
            result["osx_build_arch"] = self.osx_build_arch
        if self.container_name is not None:
            result["container_name"] = self.container_name
        if self.container is not None:
            result["container"] = self.container
        return result


class SerializableJob(Protocol):
    @property
    def duckdb_arch(self) -> str: ...

    @property
    def prefix(self) -> str | None: ...

    def to_dict(self) -> dict[str, Any]: ...


JobT = TypeVar("JobT", bound=SerializableJob)


@dataclass(slots=True)
class JobMatrix(Generic[JobT]):
    includes: list[JobT] = field(default_factory=list)

    @property
    def archs(self) -> list[str]:
        return [job.duckdb_arch for job in self.includes]

    def get(self, *, arch: str, prefix: str | None = None) -> JobT:
        matches = [
            job
            for job in self.includes
            if job.duckdb_arch == arch and (prefix is None or job.prefix == prefix)
        ]
        if len(matches) != 1:
            criteria = f"arch={arch!r}"
            if prefix is not None:
                criteria += f", prefix={prefix!r}"
            raise MatrixError(
                f"expected exactly one matrix job matching {criteria}; found {len(matches)}"
            )
        return matches[0]

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {"include": [job.to_dict() for job in self.includes]}


@dataclass(slots=True)
class PlatformMatrices(Generic[JobT]):
    linux: JobMatrix[JobT] = field(default_factory=JobMatrix)
    macos: JobMatrix[JobT] = field(default_factory=JobMatrix)
    windows: JobMatrix[JobT] = field(default_factory=JobMatrix)
    wasm: JobMatrix[JobT] = field(default_factory=JobMatrix)

    def for_platform(self, platform: Platform) -> JobMatrix[JobT]:
        if platform == "linux":
            return self.linux
        if platform == "macos":
            return self.macos
        if platform == "windows":
            return self.windows
        return self.wasm


@dataclass(slots=True)
class Matrices:
    build: PlatformMatrices[BuildJob] = field(default_factory=PlatformMatrices)
    test: PlatformMatrices[TestJob] = field(default_factory=PlatformMatrices)

    def outputs(
        self,
    ) -> Iterator[tuple[str, JobMatrix[BuildJob] | JobMatrix[TestJob]]]:
        for platform in OUTPUT_PLATFORMS:
            yield f"build_{platform}", self.build.for_platform(platform)
            yield f"test_{platform}", self.test.for_platform(platform)


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


def detect_event_type_from_env(env: Mapping[str, str] | None = None) -> str:
    resolved_env = os.environ if env is None else env
    event_path = resolved_env.get("GITHUB_EVENT_PATH", "")
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
        config_fields = {str(key) for key in config}
        unknown_config_fields = config_fields - {"include"}
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
    entry_fields = {str(key) for key in entry}
    unknown = entry_fields - allowed
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise MatrixError(f"entry {entry.get('duckdb_arch', '<unknown>')!r} has unknown fields: {fields}")
    missing = required - entry_fields
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


def parse_groups(raw: str | None) -> tuple[ExtensionGroup, ...]:
    if not raw or not raw.strip():
        raise MatrixError("groups input is required")
    groups: dict[str, dict[str, Any]] = {}
    current_group: str | None = None
    current_list_field: str | None = None

    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent != len(raw_line) - len(raw_line.lstrip()):
            raise MatrixError(f"groups line {line_number}: tabs are not supported")
        line = raw_line.strip()

        if indent == 0:
            if not line.endswith(":") or line == ":":
                raise MatrixError(f"groups line {line_number}: expected group mapping")
            current_group = line[:-1].strip()
            if not current_group:
                raise MatrixError(f"groups line {line_number}: group key cannot be empty")
            if current_group in groups:
                raise MatrixError(f"group {current_group!r} is duplicated")
            groups[current_group] = {}
            current_list_field = None
            continue

        if current_group is None:
            raise MatrixError(f"groups line {line_number}: field without group")

        if indent == 2:
            if ":" not in line:
                raise MatrixError(f"groups line {line_number}: expected field mapping")
            field, value = line.split(":", 1)
            field = field.strip()
            value = value.strip()
            if field not in {"config", "default_exclude_archs", "opt_in_archs", "toolchain"}:
                raise MatrixError(f"group {current_group!r} has unknown field: {field}")
            if field in groups[current_group]:
                raise MatrixError(f"group {current_group!r} field {field!r} is duplicated")
            if value:
                groups[current_group][field] = _parse_yaml_scalar(value)
                current_list_field = None
            else:
                if field != "config":
                    raise MatrixError(f"group {current_group!r} field {field!r} cannot be a list")
                groups[current_group][field] = []
                current_list_field = field
            continue

        if indent == 4 and current_list_field:
            if not line.startswith("- "):
                raise MatrixError(f"groups line {line_number}: expected list item")
            groups[current_group][current_list_field].append(_parse_yaml_scalar(line[2:].strip()))
            continue

        raise MatrixError(f"groups line {line_number}: unsupported indentation")

    if not groups:
        raise MatrixError("groups mapping cannot be empty")

    parsed: list[ExtensionGroup] = []
    for key in sorted(groups):
        config = groups[key]
        missing = {"config", "toolchain"} - set(config)
        if missing:
            fields = ", ".join(sorted(missing))
            raise MatrixError(f"group {key!r} is missing fields: {fields}")
        config_paths = config["config"]
        if isinstance(config_paths, str):
            paths = (config_paths,)
        elif isinstance(config_paths, list) and all(isinstance(path, str) and path for path in config_paths):
            paths = tuple(config_paths)
        else:
            raise MatrixError(f"group {key!r} config must be a string or string list")
        toolchain = config["toolchain"]
        if not isinstance(toolchain, str) or not toolchain:
            raise MatrixError(f"group {key!r} toolchain must be a non-empty string")
        for field in ("default_exclude_archs", "opt_in_archs"):
            value = config.get(field)
            if value is not None and not isinstance(value, str):
                raise MatrixError(f"group {key!r} {field} must be a string")
        parsed.append(
            ExtensionGroup(
                key=key,
                toolchain=toolchain,
                default_exclude_archs=config.get("default_exclude_archs", ""),
                opt_in_archs=config.get("opt_in_archs"),
                config_paths=paths,
            )
        )
    return tuple(parsed)


def _parse_yaml_scalar(value: str) -> str:
    if value.startswith(("'", '"')) or value.endswith(("'", '"')):
        if len(value) < 2 or value[0] != value[-1] or value[0] not in {"'", '"'}:
            raise MatrixError(f"invalid quoted scalar: {value!r}")
        return value[1:-1]
    return value


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


def load_group_config(group: ExtensionGroup) -> str:
    parts: list[str] = []
    for relative_path in group.config_paths:
        path = Path(relative_path)
        if not path.is_absolute():
            path = Path.cwd() / path
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


def linux_container_name(duckdb_arch: str, toolchain: str) -> str:
    if duckdb_arch.startswith("linux_amd64"):
        host_arch = "amd64"
    elif duckdb_arch.startswith("linux_arm64"):
        host_arch = "aarch64"
    else:
        raise MatrixError(f"unsupported Linux duckdb_arch for container: {duckdb_arch}")

    base_image = "alpine_3_22" if duckdb_arch.endswith("_musl") else "manylinux_2_28"
    return f"{base_image}_{host_arch}_{toolchain}"


def build_job(
    entry: dict[str, Any],
    group: ExtensionGroup,
    runner: list[str],
    effective_exclude_archs: str,
    effective_opt_in_archs: str,
    extension_config: str,
    image_version: str,
) -> BuildJob:
    duckdb_arch = str(entry["duckdb_arch"])
    prefix = f"{group.key}-extensions"
    osx_build_arch = str(entry["osx_build_arch"]) if "osx_build_arch" in entry else None
    container_name: str | None = None
    container: str | None = None
    if duckdb_arch.startswith("linux_"):
        container_name = linux_container_name(duckdb_arch, group.toolchain)
        if image_version:
            container = f"ghcr.io/duckdb/duckdb-ci/{container_name}:{image_version}"
    return BuildJob(
        runner=runner,
        vcpkg_target_triplet=str(entry["vcpkg_target_triplet"]),
        vcpkg_host_triplet=str(entry["vcpkg_host_triplet"]),
        duckdb_arch=duckdb_arch,
        prefix=prefix,
        artifact_name=f"{prefix}-{duckdb_arch}",
        exclude_archs=effective_exclude_archs,
        opt_in_archs=effective_opt_in_archs,
        extension_config=extension_config,
        osx_build_arch=osx_build_arch,
        container_name=container_name,
        container=container,
    )


def test_job(
    entry: dict[str, Any],
    runner: list[str],
    image_version: str,
) -> TestJob:
    duckdb_arch = str(entry["duckdb_arch"])
    osx_build_arch = str(entry["osx_build_arch"]) if "osx_build_arch" in entry else None
    container_name: str | None = None
    container: str | None = None
    if duckdb_arch.startswith("linux_"):
        container_name = linux_container_name(duckdb_arch, "main")
        if image_version:
            container = f"ghcr.io/duckdb/duckdb-ci/{container_name}:{image_version}"
    return TestJob(
        runner=runner,
        duckdb_arch=duckdb_arch,
        artifact_pattern=f"*-extensions-{duckdb_arch}",
        osx_build_arch=osx_build_arch,
        container_name=container_name,
        container=container,
    )


def compute_matrices(
    extensions: dict[str, Any],
    *,
    exclude_archs: str = "",
    opt_in_archs: str = "",
    runners: str = "{}",
    reduced_ci_mode: str = "auto",
    event_type: str = UNKNOWN,
    image_version: str = "",
    groups: str | None = None,
) -> Matrices:
    reduced_ci = resolve_reduced_ci_mode(reduced_ci_mode, event_type)
    runner_overrides = parse_runners(runners)
    extension_groups = parse_groups(groups)

    result = Matrices()
    for output_platform, config_key in PLATFORM_CONFIG_KEYS.items():
        if config_key not in extensions:
            raise MatrixError(f"missing platform in extensions.json: {config_key}")
        entries = extensions[config_key]["include"]
        build_output = result.build.for_platform(output_platform).includes
        test_entries: dict[str, tuple[dict[str, Any], list[str]]] = {}
        for group in extension_groups:
            effective_exclude_archs = combine_lists(group.default_exclude_archs, exclude_archs)
            if group.opt_in_archs is not None:
                effective_opt_in_archs = group.opt_in_archs
            elif group.key == "main":
                effective_opt_in_archs = opt_in_archs
            else:
                effective_opt_in_archs = ""
            excluded = set(split_list(effective_exclude_archs))
            opt_in = set(split_list(effective_opt_in_archs))
            extension_config = load_group_config(group)
            for entry in entries:
                if not include_entry(entry, excluded, opt_in, reduced_ci):
                    continue
                runner = resolve_runner(entry, runner_overrides)
                build_output.append(
                    build_job(
                        entry,
                        group,
                        runner,
                        effective_exclude_archs,
                        effective_opt_in_archs,
                        extension_config,
                        image_version,
                    )
                )
                test_entries.setdefault(str(entry["duckdb_arch"]), (entry, runner))
        build_output.sort(
            key=lambda job: (job.duckdb_arch, job.prefix)
        )
        test_output = result.test.for_platform(output_platform).includes
        test_output.extend(
            test_job(entry, runner, image_version)
            for entry, runner in test_entries.values()
        )
        test_output.sort(key=lambda job: job.duckdb_arch)
    return result


def render_github_output(matrices: Matrices) -> str:
    lines = []
    for key, matrix in matrices.outputs():
        payload = json.dumps(matrix.to_dict(), separators=(",", ":"), sort_keys=True)
        lines.append(f"{key}={payload}")
    return "\n".join(lines) + "\n"


RenderJobT = TypeVar("RenderJobT")


def render_readable_matrix_log(matrices: Matrices) -> str:
    lines: list[str] = []
    for platform in OUTPUT_PLATFORMS:
        _append_build_matrix_log(
            lines,
            f"build_{platform}",
            matrices.build.for_platform(platform),
        )
        _append_test_matrix_log(
            lines,
            f"test_{platform}",
            matrices.test.for_platform(platform),
        )
    return "\n".join(lines) + "\n"


def _append_build_matrix_log(
    lines: list[str],
    output_key: str,
    matrix: JobMatrix[BuildJob],
) -> None:
    columns: list[tuple[str, Callable[[BuildJob], Any]]] = [
        ("duckdb_arch", lambda job: job.duckdb_arch),
        ("runner", lambda job: job.runner),
        ("artifact_prefix", lambda job: job.prefix),
        ("artifact_name", lambda job: job.artifact_name),
        ("vcpkg_target_triplet", lambda job: job.vcpkg_target_triplet),
        ("vcpkg_host_triplet", lambda job: job.vcpkg_host_triplet),
    ]
    if any(job.container_name for job in matrix.includes):
        columns.append(("container_name", lambda job: job.container_name))
    if any(job.osx_build_arch for job in matrix.includes):
        columns.append(("osx_build_arch", lambda job: job.osx_build_arch))

    def append_details(detail_lines: list[str], job: BuildJob) -> None:
        _append_detail(detail_lines, "extension_config", job.extension_config, indent="    ")
        _append_detail(detail_lines, "exclude_archs", job.exclude_archs, indent="    ")
        _append_detail(detail_lines, "opt_in_archs", job.opt_in_archs, indent="    ")
        _append_detail(detail_lines, "container", job.container, indent="    ")

    _append_matrix_log(lines, output_key, matrix.includes, columns, append_details)


def _append_test_matrix_log(
    lines: list[str],
    output_key: str,
    matrix: JobMatrix[TestJob],
) -> None:
    columns: list[tuple[str, Callable[[TestJob], Any]]] = [
        ("duckdb_arch", lambda job: job.duckdb_arch),
        ("runner", lambda job: job.runner),
        ("artifact_pattern", lambda job: job.artifact_pattern),
    ]
    if any(job.container_name for job in matrix.includes):
        columns.append(("container_name", lambda job: job.container_name))
    if any(job.osx_build_arch for job in matrix.includes):
        columns.append(("osx_build_arch", lambda job: job.osx_build_arch))

    def append_details(detail_lines: list[str], job: TestJob) -> None:
        _append_detail(detail_lines, "container", job.container, indent="    ")

    _append_matrix_log(lines, output_key, matrix.includes, columns, append_details)


def _append_matrix_log(
    lines: list[str],
    output_key: str,
    jobs: list[RenderJobT],
    columns: list[tuple[str, Callable[[RenderJobT], Any]]],
    append_details: Callable[[list[str], RenderJobT], None],
) -> None:
    if lines:
        lines.append("")
    lines.append(f"{output_key} ({len(jobs)} {'job' if len(jobs) == 1 else 'jobs'})")
    if not jobs:
        lines.append("  No jobs")
        return

    headers = ["#", *(header for header, _ in columns)]
    rows = [
        [str(index), *(_display_value(formatter(job)) for _, formatter in columns)]
        for index, job in enumerate(jobs, start=1)
    ]
    widths = [
        max(len(header), *(len(row[column_index]) for row in rows))
        for column_index, header in enumerate(headers)
    ]
    lines.append(
        "  "
        + "  ".join(
            header.ljust(widths[column_index])
            for column_index, header in enumerate(headers)
        )
    )
    lines.append("  " + "  ".join("-" * width for width in widths))
    for row in rows:
        lines.append(
            "  "
            + "  ".join(
                value.ljust(widths[column_index])
                for column_index, value in enumerate(row)
            )
        )

    lines.append("")
    lines.append("  Details")
    for index, job in enumerate(jobs, start=1):
        lines.append(f"  Job {index}:")
        append_details(lines, job)


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return "<empty>"
    if isinstance(value, list):
        return ",".join(str(item) for item in value) if value else "<empty>"
    return str(value)


def _append_detail(lines: list[str], label: str, value: Any, *, indent: str) -> None:
    rendered = _display_value(value)
    if "\n" not in rendered:
        lines.append(f"{indent}{label}: {rendered}")
        return
    lines.append(f"{indent}{label}:")
    for line in rendered.splitlines():
        lines.append(f"{indent}  {line}")


def write_github_output(output_path: Path, matrices: Matrices) -> None:
    with output_path.open("a", encoding="utf-8") as f:
        f.write(render_github_output(matrices))
