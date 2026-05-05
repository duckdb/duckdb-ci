#!/usr/bin/env python3
"""Filter distro-specific package lists and verify installed tooling."""

from __future__ import annotations

import argparse
import dataclasses
import re
import shlex
import subprocess
import sys
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


TOOL_CHECKS: dict[str, ToolCheck] = {
    "python3": ToolCheck(
        cmd="python3 --version",
        pattern=r"(\d+\.\d+(?:\.\d+)?)",
    ),
}


def _parse_version(raw: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in raw.split("."))
    if not parts:
        raise ValueError("empty version")
    return parts


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


def _extract_version(check: ToolCheck, tool_name: str) -> tuple[int, ...]:
    try:
        result = subprocess.run(
            check.cmd,
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
            f"check command failed for {tool_name}: {check.cmd!r} (exit {result.returncode}), output={output!r}"
        )

    match = re.search(check.pattern, output)
    if match is None:
        raise RuntimeError(
            f"version pattern did not match for {tool_name}: pattern={check.pattern!r}, output={output!r}"
        )

    version = match.group(1) if match.groups() else match.group(0)

    try:
        return _parse_version(version)
    except ValueError as exc:
        raise RuntimeError(f"invalid version extracted for {tool_name}: {version!r}") from exc


def _cmd_check(args: argparse.Namespace) -> int:
    entries = _parse_packages(Path(args.packages_file), args.distro)
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

        try:
            actual = _extract_version(checker, entry.name)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        required = _parse_version(entry.version)
        if actual < required:
            actual_str = ".".join(str(p) for p in actual)
            print(
                f"ERROR: {entry.name} must be >= {entry.version}, found {actual_str}",
                file=sys.stderr,
            )
            return 1

        actual_str = ".".join(str(p) for p in actual)
        print(f"{entry.name} version check passed: {actual_str} >= {entry.version}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_list = subparsers.add_parser("list", help="Filter package list for a distro")
    parser_list.add_argument("--distro", choices=("alpine", "manylinux"), required=True)
    parser_list.add_argument("--packages-file", required=True)
    parser_list.set_defaults(func=_cmd_list)

    parser_check = subparsers.add_parser("check", help="Verify installed tooling")
    parser_check.add_argument("--distro", choices=("alpine", "manylinux"), required=True)
    parser_check.add_argument("--packages-file", required=True)
    parser_check.set_defaults(func=_cmd_check)

    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
