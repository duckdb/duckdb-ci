from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .matrix import (
    compute_matrices,
    detect_event_type_from_env,
    load_extensions_config,
    render_github_output,
    render_readable_matrix_log,
    write_github_output,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute DuckDB extension build matrices")
    parser.add_argument("--extensions", default="matrix/extensions.json")
    parser.add_argument("--exclude-archs", default="")
    parser.add_argument("--opt-in-archs", default="")
    parser.add_argument("--runners", default="{}")
    parser.add_argument("--reduced-ci-mode", default="auto")
    parser.add_argument("--image-version", default="")
    parser.add_argument("--groups", required=True)
    parser.add_argument("--out", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    event_type = detect_event_type_from_env()
    matrices = compute_matrices(
        load_extensions_config(Path(args.extensions)),
        exclude_archs=args.exclude_archs,
        opt_in_archs=args.opt_in_archs,
        runners=args.runners,
        reduced_ci_mode=args.reduced_ci_mode,
        event_type=event_type,
        image_version=args.image_version,
        groups=args.groups,
    )

    output_path = Path(args.out) if args.out else None
    if output_path is None:
        github_output = os.environ.get("GITHUB_OUTPUT", "")
        if github_output:
            output_path = Path(github_output)

    if output_path:
        write_github_output(output_path, matrices)
        sys.stdout.write(render_readable_matrix_log(matrices))
    else:
        sys.stdout.write(render_github_output(matrices))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
