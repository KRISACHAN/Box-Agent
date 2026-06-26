#!/usr/bin/env python3
"""Health check for SkillHub skill packages."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except Exception as exc:  # pragma: no cover
    yaml = None
    YAML_IMPORT_ERROR = str(exc)
else:
    YAML_IMPORT_ERROR = ""

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "references/matching-rules.md",
    "references/skillhub-policy.md",
    "references/name-resolution.md",
    "references/error-recovery.md",
    "references/capability-boundaries.md",
    "references/faq.md",
    "templates/faq.md",
]

BANNED_NAMES = {".DS_Store", ".gitignore", "LICENSE"}
BANNED_PATTERNS = ["._", ".icloud", ".tmp", ".log"]


def parse_front_matter(text: str) -> Dict[str, Any]:
    if not text.startswith("---"):
        raise ValueError("SKILL.md 缺少 YAML front matter。")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        raise ValueError("SKILL.md 的 YAML front matter 边界不完整。")
    if yaml is None:
        raise RuntimeError(f"PyYAML 不可用：{YAML_IMPORT_ERROR}")
    data = yaml.safe_load(m.group(1))
    if not isinstance(data, dict):
        raise ValueError("YAML front matter 必须解析为对象。")
    return data


def check(root: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    for rel in REQUIRED_FILES:
        if not (root / rel).exists():
            errors.append(f"缺少必要文件：{rel}")
    skill = root / "SKILL.md"
    fm: Dict[str, Any] = {}
    if skill.exists():
        try:
            fm = parse_front_matter(skill.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"YAML 校验失败：{exc}")
    for key in ["name", "version", "description", "triggers"]:
        if key not in fm or not fm.get(key):
            errors.append(f"SKILL.md 缺少必要元数据：{key}")
    if fm.get("name") != root.name and root.name.endswith("-optimized") is False:
        warnings.append("目录名与技能 name 不完全一致，请确认是否为打包目录。")
    if "zh_name" not in fm:
        warnings.append("建议补充 zh_name，提升中文名称识别准确性。")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        rel = path.relative_to(root).as_posix()
        if name in BANNED_NAMES or any(pat in name.lower() for pat in BANNED_PATTERNS):
            errors.append(f"发现不应进入上传包的文件：{rel}")
    return {
        "root": str(root),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "front_matter": fm,
        "score_hint": 100 - 15 * len(errors) - 5 * len(warnings),
    }


def main() -> None:
    root = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.cwd()
    result = check(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
