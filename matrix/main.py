from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .matrix import compute_matrices, detect_event_type_from_env, load_extensions_config, render_github_output, write_github_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute DuckDB extension build matrices")
    parser.add_argument("--extensions", default="matrix/extensions.json")
    parser.add_argument("--exclude-archs", default="")
    parser.add_argument("--opt-in-archs", default="")
    parser.add_argument("--runners", default="{}")
    parser.add_argument("--reduced-ci-mode", default="auto")
    parser.add_argument("--image-version", default="")
    parser.add_argument("--image-suffix", default="")
    parser.add_argument("--repository-owner", default="")
    parser.add_argument("--config-root", default=".")
    parser.add_argument("--out", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    event_type = detect_event_type_from_env()
    repository_owner = args.repository_owner or os.environ.get("GITHUB_REPOSITORY_OWNER", "duckdb")
    matrices = compute_matrices(
        load_extensions_config(Path(args.extensions)),
        exclude_archs=args.exclude_archs,
        opt_in_archs=args.opt_in_archs,
        runners=args.runners,
        reduced_ci_mode=args.reduced_ci_mode,
        event_type=event_type,
        image_version=args.image_version,
        image_suffix=args.image_suffix,
        repository_owner=repository_owner,
        config_root=Path(args.config_root),
    )

    if args.out:
        write_github_output(Path(args.out), matrices)
    else:
        github_output = os.environ.get("GITHUB_OUTPUT", "")
        if github_output:
            write_github_output(Path(github_output), matrices)
    sys.stdout.write(render_github_output(matrices))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
