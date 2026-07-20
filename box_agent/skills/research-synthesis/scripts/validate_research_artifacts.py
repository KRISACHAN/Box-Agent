#!/usr/bin/env python3
"""Validate deep research artifacts and Markdown footnote integrity."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


FOOTNOTE_MARKER_RE = re.compile(r"\[\^([A-Za-z0-9_.:-]+)\]")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_.:-]+)\]:", re.MULTILINE)


ROUTE_REQUIRED = {
    "A": ["{topic}_cross_verification.md", "{topic}_insight.md"],
    "B": ["{topic}_cross_verification.md", "{topic}_insight.md"],
    "C": [
        "{topic}_file_analysis.md",
        "{topic}_cross_verification.md",
        "{topic}_insight.md",
    ],
    "D": [
        "{topic}_file_analysis.md",
        "{topic}_cross_verification.md",
        "{topic}_insight.md",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate deep research output files for a topic."
    )
    parser.add_argument("--research-dir", required=True, type=Path)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--route", required=True, choices=sorted(ROUTE_REQUIRED))
    parser.add_argument("--min-dimensions", type=int, default=10)
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report path for downstream workflow checkpoints.",
    )
    parser.add_argument(
        "--allow-missing-footnotes",
        action="store_true",
        help="Only warn when footnote markers lack definitions.",
    )
    return parser.parse_args()


def write_report(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def collect_footnotes(path: Path) -> tuple[set[str], set[str]]:
    text = path.read_text(encoding="utf-8")
    definitions = set(FOOTNOTE_DEF_RE.findall(text))
    markers = set(FOOTNOTE_MARKER_RE.findall(text))
    return markers - definitions, definitions


def main() -> int:
    args = parse_args()
    research_dir = args.research_dir
    errors: list[str] = []
    warnings: list[str] = []
    dim_files: list[Path] = []
    wide_files: list[Path] = []
    files_to_check: list[Path] = []

    if not research_dir.exists():
        errors.append(f"research dir does not exist: {research_dir}")
    elif not research_dir.is_dir():
        errors.append(f"research path is not a directory: {research_dir}")

    if not errors:
        required = [name.format(topic=args.topic) for name in ROUTE_REQUIRED[args.route]]
        dim_files = sorted(research_dir.glob(f"{args.topic}_dim*.md"))
        wide_files = sorted(research_dir.glob(f"{args.topic}_wide*.md"))

        for file_name in required:
            if not (research_dir / file_name).exists():
                errors.append(f"missing required file: {file_name}")

        if len(dim_files) < args.min_dimensions:
            errors.append(
                f"expected at least {args.min_dimensions} dimension files, found {len(dim_files)}"
            )

        if args.route == "A" and not wide_files:
            errors.append("route A requires at least one wide exploration file")

        files_to_check = sorted(
            {
                *dim_files,
                *wide_files,
                *(research_dir / file_name for file_name in required),
                *(research_dir.glob(f"{args.topic}_final.md")),
            }
        )

        for path in files_to_check:
            if not path.exists():
                continue
            missing_defs, definitions = collect_footnotes(path)
            if missing_defs:
                message = (
                    f"{path.name}: missing footnote definitions for "
                    + ", ".join(sorted(missing_defs))
                )
                if args.allow_missing_footnotes:
                    warnings.append(message)
                else:
                    errors.append(message)
            if "[^" in path.read_text(encoding="utf-8") and not definitions:
                errors.append(f"{path.name}: contains footnote markers but no definitions")

    report_payload: dict[str, object] = {
        "ok": not errors,
        "validator": "research-synthesis",
        "route": args.route,
        "topic": args.topic,
        "research_dir": str(research_dir.resolve()),
        "min_dimensions": args.min_dimensions,
        "dimension_count": len(dim_files),
        "wide_count": len(wide_files),
        "files_checked": [str(path.resolve()) for path in files_to_check if path.exists()],
        "issues": errors,
        "warnings": warnings,
    }
    write_report(args.report, report_payload)

    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"OK: {args.route} artifacts for topic '{args.topic}' validated in {research_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
