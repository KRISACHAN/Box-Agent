#!/usr/bin/env python3
"""Validate the SkillHub release package before upload."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - optional developer dependency
    yaml = None

EXPECTED_VERSION = "1.2.8"
ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "package.json",
    "scripts/validate_skill.py",
    "scripts/render_text_overlay.py",
    "references/quick-start-3min.md",
    "references/legal-disclaimer.md",
    "references/visual-review-checklist.md",
    "references/user-upload-policy.md",
    "references/platform-compatibility.md",
    "references/font-compatibility-guide.md",
    "references/error-code-guide.md",
    "references/config-parameter-reference.md",
    "references/faq.md",
    "examples/text-overlay-config-example.json",
    "examples/text-overlay-config-commented.md",
    "examples/midfield-master-case.md",
    "examples/champion-forward-case.md",
]

TEMP_NAMES = {".DS_Store", ".gitignore", "LICENSE", "validate-debug.log"}
TEMP_SUFFIXES = {".log", ".pid", ".tmp"}
PROCESS_WORDS = ("assessment", "ret-test", "review-report", "final-launch-note")
PLACEHOLDERS = ("TODO", "TBD", "待补充", "占位", "示例待完善")
SKILL_REQUIRED_TERMS = ["触发方式", "用户使用引导模式", "标准执行流程", "异常处理", "合规门禁", "FAQ"]
README_REQUIRED_TERMS = ["我该从哪里开始", "字体", "错误码", "参数范围", "FAQ", "平台兼容"]
REFERENCE_TERMS = [
    "references/platform-compatibility.md",
    "references/font-compatibility-guide.md",
    "references/error-code-guide.md",
    "references/config-parameter-reference.md",
    "references/faq.md",
]
ERROR_CODES = [
    "ERR_FILE_NOT_FOUND",
    "ERR_CONFIG_JSON_INVALID",
    "ERR_CONFIG_FIELD_MISSING",
    "ERR_CONFIG_VALUE_RANGE",
    "ERR_IMAGE_FORMAT_UNSUPPORTED",
    "ERR_IMAGE_MODE_UNSUPPORTED",
    "ERR_FONT_NOT_FOUND",
    "ERR_OUTPUT_PATH_INVALID",
    "ERR_COMPLIANCE_RISK_HIGH",
]
EXAMPLE_SECTIONS = ["用户输入", "风险判断", "安全转译", "Prompt", "质检"]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def check_required_files() -> None:
    missing = [rel for rel in REQUIRED_FILES if not (ROOT / rel).is_file()]
    if missing:
        fail("缺少必备文件: " + ", ".join(missing))


def parse_front_matter(text: str) -> dict:
    match = re.search(r"^---\n(?P<body>.+?)\n---", text, re.S)
    if not match:
        fail("SKILL.md 缺少 YAML front matter")
    body = match.group("body")
    if yaml is not None:
        try:
            parsed = yaml.safe_load(body)
        except Exception as exc:  # noqa: BLE001
            fail(f"SKILL.md YAML front matter 无法解析: {exc}")
        if not isinstance(parsed, dict):
            fail("SKILL.md YAML front matter 不是键值结构")
        return parsed
    parsed = {}
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            fail(f"SKILL.md YAML front matter 存在无法解析的行: {line}")
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip().strip('"\'')
    return parsed


def check_versions() -> None:
    skill = read("SKILL.md")
    readme = read("README.md")
    visual_checklist = read("references/visual-review-checklist.md")
    package = json.loads(read("package.json"))
    front_matter = parse_front_matter(skill)

    if str(front_matter.get("version")) != EXPECTED_VERSION:
        fail("SKILL.md front matter 版本号不一致")
    if package.get("version") != EXPECTED_VERSION:
        fail("package.json 版本号不一致")
    if f"v{EXPECTED_VERSION}" not in readme.splitlines()[0]:
        fail("README.md 标题版本号不一致")
    if f"v{EXPECTED_VERSION}" not in visual_checklist.splitlines()[0]:
        fail("visual-review-checklist.md 标题版本号不一致")

    stale_versions = ["1.2." + suffix for suffix in ("6", "7")]
    stale_patterns = tuple(prefix + version for version in stale_versions for prefix in ("", "v"))
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".yaml", ".yml", ".json", ".py"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        content = path.read_text(encoding="utf-8", errors="ignore")
        for stale in stale_patterns:
            if stale in content:
                fail(f"发现旧版本号 {stale}: {rel}")


def check_entry_guidance() -> None:
    skill = read("SKILL.md")
    readme = read("README.md")
    for term in SKILL_REQUIRED_TERMS:
        if term not in skill:
            fail(f"SKILL.md 缺少关键引导: {term}")
    for term in README_REQUIRED_TERMS:
        if term not in readme:
            fail(f"README.md 缺少用户导航: {term}")
    for term in REFERENCE_TERMS:
        if term not in skill or term not in readme:
            fail(f"入口文档未引用参考文件: {term}")


def check_error_guides() -> None:
    guide = read("references/error-code-guide.md")
    script = read("scripts/render_text_overlay.py")
    for code in ERROR_CODES:
        if code not in guide:
            fail(f"错误码指南缺少: {code}")
    required_script_codes = [c for c in ERROR_CODES if c != "ERR_COMPLIANCE_RISK_HIGH"]
    for code in required_script_codes:
        if code not in script:
            fail(f"叠字脚本缺少错误码: {code}")
    if "--dry-run" not in script:
        fail("叠字脚本缺少 dry-run 支持")
    if "WARN_FONT_FALLBACK" not in script:
        fail("叠字脚本缺少字体 fallback 提示")


def check_examples() -> None:
    for rel in ["examples/midfield-master-case.md", "examples/champion-forward-case.md"]:
        text = read(rel)
        missing = [s for s in EXAMPLE_SECTIONS if s not in text]
        if missing:
            fail(f"示例不完整 {rel}，缺少: {missing}")
    cfg = json.loads(read("examples/text-overlay-config-example.json"))
    if "text_layers" not in cfg or not cfg["text_layers"]:
        fail("叠字配置缺少 text_layers")
    for idx, layer in enumerate(cfg["text_layers"]):
        if "font_fallback" not in layer:
            fail(f"叠字配置 text_layers[{idx}] 缺少 font_fallback")
        size = layer.get("font_size")
        if not isinstance(size, (int, float)) or not 12 <= size <= 220:
            fail(f"叠字配置 text_layers[{idx}].font_size 超出范围")


def check_temp_and_process_files() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        low = rel.lower()
        if path.name in TEMP_NAMES or path.suffix.lower() in TEMP_SUFFIXES or low.endswith("~"):
            fail(f"上传包不应包含运行态文件: {rel}")
        if "reports" in path.relative_to(ROOT).parts or any(word in low for word in PROCESS_WORDS):
            fail(f"上传包不应包含过程文件: {rel}")
        if path.resolve() != Path(__file__).resolve() and path.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".py", ".html"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for placeholder in PLACEHOLDERS:
                if placeholder in text:
                    fail(f"文件包含占位内容 {placeholder}: {rel}")


def main() -> int:
    check_required_files()
    check_versions()
    check_entry_guidance()
    check_error_guides()
    check_examples()
    check_temp_and_process_files()
    print("PASS: skill package validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
