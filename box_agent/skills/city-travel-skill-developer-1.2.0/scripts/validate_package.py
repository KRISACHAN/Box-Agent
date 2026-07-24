#!/usr/bin/env python3
"""Validate a City Travel Skill Developer SkillHub package."""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

try:
    import yaml
except Exception:
    yaml = None

ROOT_REQUIRED = ["SKILL.md", "README.md", "package.json"]
REQUIRED_DIRS = ["references", "playbooks", "templates", "qa", "scripts", "examples"]
FORBIDDEN_NAMES = {".DS_Store", "Thumbs.db", ".gitignore", "LICENSE"}
FORBIDDEN_EXTS = {".docx", ".doc", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".gif", ".zip"}
V12_REQUIRED = [
    "templates/evidence-source-map-template.md",
    "templates/trace-depth-scorecard-template.md",
    "templates/regression-matrix-template.md",
    "templates/prelaunch-review-template.md",
    "templates/core-asset-inventory-template.md",
    "playbooks/prelaunch-enhancement-sprint.md",
    "playbooks/whitelist-packaging.md",
    "qa/artifact-contamination-check.md",
    "qa/prelaunch-gate.md",
]
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def history_markers():
    def s(parts):
        return "[" + "".join(parts) + "]"
    return [
        s(["F", "ull ", "tool", "-call argument ", "omitted ", "from model history"]),
        s(["F", "ull ", "file content ", "omitted ", "from model history"]),
        s(["F", "ull ", "tool output ", "omitted ", "from model history"]),
    ]


def local_path_patterns():
    return [r"/" + r"Us" + r"ers/[^\s)]+", r"/mnt/data/", r"local-file://"]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_front_matter(text: str):
    if not text.startswith("---\n"):
        return None, "missing front matter"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "front matter not closed"
    raw = text[4:end]
    if yaml is None:
        return None, "pyyaml unavailable"
    try:
        data = yaml.safe_load(raw) or {}
    except Exception as exc:
        return None, f"YAML parse error: {exc}"
    return data, None


def iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def validate(root: Path):
    issues = []
    warnings = []

    for name in ROOT_REQUIRED:
        if not (root / name).is_file():
            issues.append(f"missing root file: {name}")
    for name in REQUIRED_DIRS:
        if not (root / name).is_dir():
            warnings.append(f"missing recommended dir: {name}")
    for name in V12_REQUIRED:
        if not (root / name).is_file():
            issues.append(f"missing v1.2 required asset: {name}")

    skill = root / "SKILL.md"
    if skill.is_file():
        text = read_text(skill)
        meta, err = parse_front_matter(text)
        if err:
            issues.append(err)
        else:
            name = str(meta.get("name", ""))
            desc = str(meta.get("description", ""))
            version = str(meta.get("version", ""))
            if not SLUG_RE.match(name):
                issues.append(f"invalid slug name: {name}")
            if len(desc) < 120:
                warnings.append("description may be too thin")
            if version and not version.startswith("1.2"):
                warnings.append(f"version not marked as v1.2.x: {version}")

    text_files = []
    for file in iter_files(root):
        rel = file.relative_to(root)
        parts = rel.parts
        if any(part.startswith(".") for part in parts):
            issues.append(f"hidden file in package: {rel}")
        if file.name in FORBIDDEN_NAMES:
            issues.append(f"forbidden file: {rel}")
        if file.suffix.lower() in FORBIDDEN_EXTS:
            issues.append(f"unsupported or nested artifact: {rel}")
        if file.suffix.lower() in {".md", ".json", ".py", ".txt"}:
            text_files.append(file)

    markers = history_markers()
    patterns = local_path_patterns()
    for file in text_files:
        text = read_text(file)
        rel = file.relative_to(root)
        for marker in markers:
            if marker in text:
                issues.append(f"history placeholder pollution: {rel}")
        if rel.as_posix() != "scripts/validate_package.py":
            for pattern in patterns:
                if re.search(pattern, text):
                    issues.append(f"absolute/local path exposure: {rel}")
        if rel.as_posix() != "qa/artifact-contamination-check.md":
            if "真实线上日志" in text and "不代表真实线上用户日志" not in text:
                warnings.append(f"check simulated regression wording: {rel}")

    return {"ok": not issues, "issues": issues, "warnings": warnings}


def validate_zip(zip_path: Path):
    issues = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    if "SKILL.md" not in names:
        issues.append("zip root missing SKILL.md")
    if any(name.endswith(".zip") for name in names):
        issues.append("zip contains nested zip")
    for name in names:
        p = Path(name)
        if any(part.startswith(".") for part in p.parts if part):
            issues.append(f"zip hidden file: {name}")
        if p.name in FORBIDDEN_NAMES:
            issues.append(f"zip forbidden file: {name}")
        if p.suffix.lower() in FORBIDDEN_EXTS:
            issues.append(f"zip unsupported or nested artifact: {name}")
    for required in ["SKILL.md", "README.md", "package.json"] + V12_REQUIRED:
        if required not in names:
            issues.append(f"zip missing required asset: {required}")
    return {"ok": not issues, "issues": issues, "warnings": []}


def main(argv):
    if len(argv) < 2:
        print("Usage: validate_package.py <skill-dir-or-zip> [--json]")
        return 2
    target = Path(argv[1]).resolve()
    as_json = "--json" in argv
    result = validate_zip(target) if target.suffix == ".zip" else validate(target)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PASS" if result["ok"] else "FAIL")
        for item in result["issues"]:
            print(f"ISSUE: {item}")
        for item in result["warnings"]:
            print(f"WARN: {item}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
