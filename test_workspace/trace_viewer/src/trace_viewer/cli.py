"""Command-line entry point for the trusted-network viewer."""

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from trace_viewer.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Browse offline ACP evaluation output")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    uvicorn.run(create_app(args.repo_root), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
