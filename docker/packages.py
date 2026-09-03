#!/usr/bin/env python
"""Filter distro-specific package lists and verify installed tooling."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class PackageEntry:
    name: str
    op: str | None = None
    version: str | None = None


@dataclasses.dataclass(frozen=True)
class ToolCheck:
    cmd: str
    pattern: str
    additional_cmds: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ToolArtifact:
    archive_name: str
    archive_url: str
    checksum_url: str
    binary_member: str


TOOL_CHECKS: dict[str, ToolCheck] = {
    "cmake": ToolCheck(
        cmd="cmake --version",
        pattern=r"cmake version (\d+(?:\.\d+)*)",
    ),
    "clangd-20": ToolCheck(
        cmd="clangd-20 --version",
        pattern=r"clangd version (\d+(?:\.\d+)*)",
    ),
    "lcov": ToolCheck(
        cmd="lcov --version",
        pattern=r"LCOV version (\d+(?:\.\d+)*)(?:-\d+)?",
    ),
    "python3": ToolCheck(
        cmd="python --version",
        pattern=r"(\d+\.\d+(?:\.\d+)?)",
    ),
    "py3-requests": ToolCheck(
        cmd='python -c "import requests; print(requests.__version__)"',
        pattern=r"(\d+(?:\.\d+)*)",
    ),
    "py3-pytest": ToolCheck(
        cmd="pytest --version",
        pattern=r"pytest (\d+(?:\.\d+)*)",
        additional_cmds=("python -m pytest --version",),
    ),
    "pytest": ToolCheck(
        cmd="pytest --version",
        pattern=r"pytest (\d+(?:\.\d+)*)",
        additional_cmds=("python -m pytest --version",),
    ),
    "requests": ToolCheck(
        cmd='python -c "import requests; print(requests.__version__)"',
        pattern=r"(\d+(?:\.\d+)*)",
    ),
    "rclone": ToolCheck(
        cmd="rclone version",
        pattern=r"rclone v(\d+(?:\.\d+)*)",
    ),
    "s5cmd": ToolCheck(
        cmd="s5cmd version",
        pattern=r"v(\d+(?:\.\d+)*)",
    ),
    "clang": ToolCheck(
        cmd="clang++ --version",
        pattern=r"clang version (\d+(?:\.\d+)*)",
    ),
    "clang20": ToolCheck(
        cmd="clang++ --version",
        pattern=r"clang version (\d+(?:\.\d+)*)",
    ),
    "compiler-rt": ToolCheck(
        cmd="clang --print-runtime-dir",
        pattern=r"/clang/(\d+(?:\.\d+)*)",
    ),
    "llvm": ToolCheck(
        cmd="llvm-symbolizer --version",
        pattern=r"LLVM version (\d+(?:\.\d+)*)",
    ),
    "llvm20": ToolCheck(
        cmd="llvm-symbolizer --version",
        pattern=r"LLVM version (\d+(?:\.\d+)*)",
    ),
}


def _parse_version(raw: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in raw.split("."))
    if not parts:
        raise ValueError("empty version")
    return parts


def _parse_install_spec(raw: str) -> tuple[str, str]:
    if raw.count("@") != 1:
        raise ValueError(f"invalid install specification {raw!r}; expected NAME@VERSION")

    name, version = raw.split("@", 1)
    if not name or not re.fullmatch(r"\d+(?:\.\d+)*", version):
        raise ValueError(f"invalid install specification {raw!r}; expected NAME@VERSION")
    if name not in ("cmake", "rclone", "s5cmd"):
        raise ValueError(f"unsupported install tool {name!r}")

    return name, version


def _target_architecture() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "amd64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    raise RuntimeError(f"unsupported architecture for tool installation: {machine!r}")


def _tool_artifact(name: str, version: str) -> ToolArtifact:
    if platform.system() != "Linux":
        raise RuntimeError(f"tool installation is only supported on Linux, found {platform.system()!r}")

    architecture = _target_architecture()
    if name == "s5cmd":
        release_arch = "64bit" if architecture == "amd64" else "arm64"
        archive_name = f"s5cmd_{version}_Linux-{release_arch}.tar.gz"
        release_url = f"https://github.com/peak/s5cmd/releases/download/v{version}"
        return ToolArtifact(
            archive_name=archive_name,
            archive_url=f"{release_url}/{archive_name}",
            checksum_url=f"{release_url}/s5cmd_checksums.txt",
            binary_member="s5cmd",
        )

    archive_name = f"rclone-v{version}-linux-{architecture}.zip"
    release_url = f"https://downloads.rclone.org/v{version}"
    return ToolArtifact(
        archive_name=archive_name,
        archive_url=f"{release_url}/{archive_name}",
        checksum_url=f"{release_url}/SHA256SUMS",
        binary_member=f"rclone-v{version}-linux-{architecture}/rclone",
    )


def _parse_packages(packages_file: Path, distro: str) -> list[PackageEntry]:
    packages: list[PackageEntry] = []
    for raw_line in packages_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "#" in line:
            package, marker = line.split("#", 1)
            package = package.strip()
            marker = marker.strip()
            if marker and marker != distro:
                continue
            line = package

        if not line:
            continue

        parts = line.split()
        if len(parts) == 1:
            packages.append(PackageEntry(name=parts[0]))
            continue
        if len(parts) == 3:
            name, op, version = parts
            packages.append(PackageEntry(name=name, op=op, version=version))
            continue

        raise ValueError(f"Invalid package line in {packages_file}: {raw_line!r}")
    return packages


def _cmd_list(args: argparse.Namespace) -> int:
    packages = _parse_packages(Path(args.packages_file), args.distro)
    print(" ".join(shlex.quote(pkg.name) for pkg in packages))
    return 0


def _extract_version(check: ToolCheck, tool_name: str, cmd: str) -> tuple[int, ...]:
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover
        raise RuntimeError(f"failed to execute check command for {tool_name}: {exc}") from exc

    output = f"{result.stdout}\n{result.stderr}".strip()
    if result.returncode != 0:
        raise RuntimeError(
            f"check command failed for {tool_name}: {cmd!r} (exit {result.returncode}), output={output!r}"
        )

    match = re.search(check.pattern, output)
    if match is None:
        raise RuntimeError(
            f"version pattern did not match for {tool_name}: command={cmd!r}, "
            f"pattern={check.pattern!r}, output={output!r}"
        )

    version = match.group(1) if match.groups() else match.group(0)

    try:
        return _parse_version(version)
    except ValueError as exc:
        raise RuntimeError(f"invalid version extracted for {tool_name}: {version!r}") from exc


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "duckdb-ci-packages"})
    try:
        with urllib.request.urlopen(request) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(f"failed to download {url!r}: {exc}") from exc


def _expected_checksum(checksum_file: Path, archive_name: str) -> str:
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == archive_name:
            checksum = parts[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", checksum):
                return checksum
            break
    raise RuntimeError(f"no valid SHA-256 checksum found for {archive_name!r}")


def _verify_checksum(archive: Path, checksum_file: Path) -> None:
    expected = _expected_checksum(checksum_file, archive.name)
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(f"SHA-256 mismatch for {archive.name!r}: expected {expected}, found {actual}")


def _extract_binary(artifact: ToolArtifact, archive: Path, destination: Path) -> None:
    try:
        if artifact.archive_name.endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as bundle:
                member = bundle.getmember(artifact.binary_member)
                if not member.isfile():
                    raise RuntimeError(f"archive member is not a file: {artifact.binary_member!r}")
                source = bundle.extractfile(member)
                if source is None:  # pragma: no cover
                    raise RuntimeError(f"failed to read archive member {artifact.binary_member!r}")
                with source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
            return

        with zipfile.ZipFile(archive) as bundle:
            member = bundle.getinfo(artifact.binary_member)
            if member.is_dir():
                raise RuntimeError(f"archive member is not a file: {artifact.binary_member!r}")
            with bundle.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    except (KeyError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise RuntimeError(
            f"failed to extract {artifact.binary_member!r} from {artifact.archive_name!r}: {exc}"
        ) from exc


def _installed_version(name: str) -> tuple[int, ...] | None:
    checker = TOOL_CHECKS[name]
    try:
        return _extract_version(checker, name, checker.cmd)
    except RuntimeError:
        return None


def _install_binary(name: str, source: Path) -> None:
    destination = Path("/usr/local/bin") / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_destination = destination.with_name(f".{name}.tmp")
    try:
        shutil.copyfile(source, temporary_destination)
        temporary_destination.chmod(0o755)
        os.replace(temporary_destination, destination)
    finally:
        temporary_destination.unlink(missing_ok=True)


def _install_cmake(version: str) -> None:
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        f"cmake=={version}",
    ]
    if Path("/etc/alpine-release").exists():
        command.insert(-1, "--break-system-packages")

    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"failed to install cmake {version} with pip: {exc}") from exc


def _install_tool(name: str, version: str) -> None:
    required = _parse_version(version)
    installed = _installed_version(name)
    satisfies_requirement = installed is not None and (
        installed == required if name == "cmake" else installed >= required
    )
    if satisfies_requirement:
        installed_str = ".".join(str(part) for part in installed)
        operator = "==" if name == "cmake" else ">="
        print(f"{name} installation skipped: {installed_str} {operator} {version}")
        return

    if name == "cmake":
        _install_cmake(version)
    else:
        artifact = _tool_artifact(name, version)
        with tempfile.TemporaryDirectory(prefix=f"{name}-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            archive = temporary_path / artifact.archive_name
            checksum_file = temporary_path / "checksums.txt"
            binary = temporary_path / name

            _download(artifact.archive_url, archive)
            _download(artifact.checksum_url, checksum_file)
            _verify_checksum(archive, checksum_file)
            _extract_binary(artifact, archive, binary)
            _install_binary(name, binary)

    actual = _installed_version(name)
    if actual != required:
        actual_str = "unavailable" if actual is None else ".".join(str(part) for part in actual)
        raise RuntimeError(f"{name} installation expected version {version}, found {actual_str}")
    print(f"{name} installation passed: {version}")


def _check_entries(entries: list[PackageEntry]) -> int:
    constrained = [entry for entry in entries if entry.op is not None and entry.version is not None]

    if not constrained:
        print("No constrained package checks found.")
        return 0

    for entry in constrained:
        if entry.op != ">=":
            print(
                f"ERROR: unsupported operator for {entry.name}: {entry.op!r}. Only '>=' is supported.",
                file=sys.stderr,
            )
            return 1

        checker = TOOL_CHECKS.get(entry.name)
        if checker is None:
            print(
                f"ERROR: no version checker implemented for constrained package {entry.name!r}",
                file=sys.stderr,
            )
            return 1

        required = _parse_version(entry.version)
        commands = (checker.cmd, *checker.additional_cmds)
        for cmd in commands:
            try:
                actual = _extract_version(checker, entry.name, cmd)
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1

            actual_str = ".".join(str(p) for p in actual)
            if actual < required:
                print(
                    f"ERROR: {entry.name} must be >= {entry.version} using {cmd!r}, found {actual_str}",
                    file=sys.stderr,
                )
                return 1

            command_suffix = f" using {cmd!r}" if len(commands) > 1 else ""
            print(f"{entry.name} version check passed{command_suffix}: {actual_str} >= {entry.version}")

    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    entries = _parse_packages(Path(args.packages_file), args.distro)
    return _check_entries(entries)


def _cmd_install(args: argparse.Namespace) -> int:
    tools: list[tuple[str, str]] = []
    names: set[str] = set()
    for raw_spec in args.tools:
        name, version = _parse_install_spec(raw_spec)
        if name in names:
            raise ValueError(f"duplicate install tool {name!r}")
        names.add(name)
        tools.append((name, version))

    for name, version in tools:
        _install_tool(name, version)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_list = subparsers.add_parser("list", help="Filter package list for a distro")
    parser_list.add_argument("--distro", choices=("alpine", "manylinux", "ubuntu"), required=True)
    parser_list.add_argument("--packages-file", required=True)
    parser_list.set_defaults(func=_cmd_list)

    parser_check = subparsers.add_parser("check", help="Verify installed tooling")
    parser_check.add_argument("--distro", choices=("alpine", "manylinux", "ubuntu"), required=True)
    parser_check.add_argument("--packages-file", required=True)
    parser_check.set_defaults(func=_cmd_check)

    parser_install = subparsers.add_parser("install", help="Install versioned standalone tools")
    parser_install.add_argument("tools", nargs="+", metavar="NAME@VERSION")
    parser_install.set_defaults(func=_cmd_install)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
