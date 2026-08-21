"""Command-line entry point for the offline ACP evaluation runner."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from acp_eval.batch_runner import run_batch


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least one")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acp-eval",
        description="Capture self-contained offline Box-Agent ACP evaluations.",
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=_positive_float, default=2700.0)
    parser.add_argument("--parallelism", type=_positive_int, default=1)
    parser.add_argument(
        "--retry-terminal",
        action="store_true",
        help="create a new immutable attempt even when the latest is terminal",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_batch(
            dataset=args.dataset,
            output_dir=args.run_dir,
            repo_root=args.repo_root,
            timeout_seconds=args.timeout_seconds,
            parallelism=args.parallelism,
            case_ids=args.case_id,
            retry_terminal=args.retry_terminal,
        )
    except (OSError, ValueError) as error:
        print(f"acp-eval: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
