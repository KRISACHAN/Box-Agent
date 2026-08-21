#!/usr/bin/env python3
"""Static checks for film-tv-license-application-assistant. No portal automation."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except Exception:
    yaml = None

ROOT_NAME = "film-tv-license-application-assistant"
FORBIDDEN_FILES = {".DS_Store", "Thumbs.db", ".baiduyun.uploading.cfg"}
UNIX_HOME = "/Users/"
REQUIRED = [
    "SKILL.md",
    "README.md",
    "package.json",
    "references/source-map.md",
    "references/license-routing.md",
    "references/playbook-dragon-mark.md",
    "references/playbook-net-mark.md",
    "references/playbook-tv-drama.md",
    "references/playbook-micro-drama-triage.md",
    "references/playbook-coproduction.md",
    "references/playbook-vr-film.md",
    "references/qualification-gates.md",
    "references/materials-checklists.md",
    "references/tech-specs.md",
    "references/post-license-compliance.md",
    "references/official-links.md",
    "references/faq-rules.md",
    "references/evidence-grades.md",
    "references/policy-timeline.md",
    "references/honest-boundaries.md",
    "references/phrasebook.md",
    "references/sensitive-topics-tree.md",
    "references/promo-compliance-check.md",
    "references/common-errors.md",
    "references/playbook-micro-drama-class2-3.md",
    "references/provincial-windows.md",
    "references/playbook-production-license.md",
    "references/policy-watch.md",
    "templates/delivery-pack.md",
    "templates/intake-card.md",
    "templates/diagnosis-card.md",
    "templates/materials-checklist.md",
    "templates/correction-response.md",
    "templates/form-field-drafts.md",
    "examples/case-theatrical-feature.md",
    "examples/case-online-movie.md",
    "examples/case-tv-series.md",
    "examples/case-micro-drama-triage.md",
    "examples/case-personal-filmmaker-nogo.md",
    "examples/case-net-to-theatrical.md",
    "examples/case-vr-feature.md",
    "examples/case-coproduction.md",
    "qa/smoke-tests.md",
    "qa/prd-implementation-audit.md",
    "qa/release-gate.md",
]


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        raise ValueError("SKILL.md missing YAML front matter")
    if yaml is None:
        return {"_raw": m.group(1)}
    data = yaml.safe_load(m.group(1)) or {}
    if not isinstance(data, dict):
        raise ValueError("front matter must be a mapping")
    return data


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED:
        if not (root / rel).exists():
            errors.append(f"missing: {rel}")

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name in FORBIDDEN_FILES or "baiduyun" in p.name.lower():
            errors.append(f"forbidden file: {p.relative_to(root)}")

    skill = root / "SKILL.md"
    if skill.exists():
        text = skill.read_text(encoding="utf-8")
        try:
            meta = parse_frontmatter(text)
        except ValueError as e:
            errors.append(str(e))
            meta = {}
        name = str(meta.get("name", "")).strip()
        desc = str(meta.get("description", "")).strip()
        extra = set(meta.keys()) - {"name", "description", "license", "allowed-tools", "metadata", "_raw"}
        if extra:
            errors.append(f"unexpected frontmatter keys: {sorted(extra)}")
        if name != ROOT_NAME:
            errors.append(f"SKILL.md name must be {ROOT_NAME}")
        if "<" in desc or ">" in desc:
            errors.append("description contains angle brackets")
        if len(desc) > 1024:
            errors.append(f"description too long: {len(desc)}")
        if "一类" not in text or "硬停" not in text:
            errors.append("SKILL.md missing core routing or hard-stop language")

    pkg = root / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text(encoding="utf-8"))
        if data.get("name") != ROOT_NAME:
            errors.append("package.json.name mismatch")

    skip_suffix = {".png", ".jpg", ".pdf", ".zip", ".skill"}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() in skip_suffix:
            continue
        try:
            blob = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if UNIX_HOME in blob and p.name != "validate_package.py":
            errors.append(f"absolute path token in {p.relative_to(root)}")

    return errors


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    errors = validate(root)
    if errors:
        print("FAIL")
        for e in errors:
            print(f"- {e}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
