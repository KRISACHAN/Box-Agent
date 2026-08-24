"""Roadmap-specific validation for trusted HTML artifact metadata."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

_HTML_ARTIFACT_METADATA_LIMIT = 16 * 1024 * 1024
_ROADMAP_LAYOUT_ID = "roadmap-swimlane-v1"
_ROADMAP_GENERATOR = "Box Agent Roadmap Artifact v1"
_ROADMAP_JSON_SCRIPT_IDS = frozenset(
    {
        "deck-document",
        "roadmap-geometry",
        "roadmap-diagnostics",
        "roadmap-pending-questions",
        "roadmap-palette",
        "roadmap-editor-metadata",
    }
)


@lru_cache(maxsize=1)
def _roadmap_spec_validator() -> Draft202012Validator:
    references = Path(__file__).resolve().parent / "skills" / "roadmap" / "references"
    draft_schema = json.loads(
        (references / "roadmap-draft.schema.json").read_text(encoding="utf-8")
    )
    spec_schema = json.loads(
        (references / "roadmap-spec.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(
        draft_schema["$id"], Resource.from_contents(draft_schema)
    )
    return Draft202012Validator(spec_schema, registry=registry)


def _safe_inline_script(value: str) -> str:
    return re.sub(r"</script", r"<\\/script", value, flags=re.IGNORECASE)


def _runtime_module(source: str, name: str, require_body: str) -> str:
    return "\n".join(
        (
            f"(function(){{const module={{exports:{{}}}};const exports=module.exports;{require_body}",
            _safe_inline_script(source),
            f";window.{name}=module.exports;}})();",
        )
    )


@lru_cache(maxsize=1)
def _trusted_roadmap_runtime_surface() -> tuple[dict[str, str], str]:
    skill_root = Path(__file__).resolve().parent / "skills" / "roadmap"
    scripts = skill_root / "scripts"
    contract_source = (scripts / "roadmap_contract_core.js").read_text(encoding="utf-8")
    geometry_source = (scripts / "roadmap_geometry_core.js").read_text(encoding="utf-8")
    editor_source = (skill_root / "runtime" / "roadmap-editor.js").read_text(
        encoding="utf-8"
    )
    contract_require = (
        'const require=(request)=>{if(request==="crypto")return '
        '{createHash:()=>{throw new Error("crypto hashing is unavailable in the Roadmap '
        'editor runtime")}};throw new Error(`Unsupported runtime module: ${request}`);};'
    )
    geometry_require = (
        'const require=(request)=>{if(request==="./roadmap_contract_core.js")return '
        'window.__roadmapContractCore;throw new Error(`Unsupported runtime module: '
        '${request}`);};'
    )
    return (
        {
            "contract-core": _runtime_module(
                contract_source, "__roadmapContractCore", contract_require
            ),
            "geometry-core": _runtime_module(
                geometry_source, "__roadmapGeometryCore", geometry_require
            ),
            "editor": _safe_inline_script(editor_source).strip(),
        },
        (skill_root / "runtime" / "roadmap.css").read_text(encoding="utf-8"),
    )


def _has_trusted_roadmap_runtime_surface(content: str) -> bool:
    markup = re.sub(
        r"<(?:script|style)\b[^>]*>[\s\S]*?</(?:script|style)\s*>",
        "",
        content,
        flags=re.IGNORECASE,
    )
    if re.search(r"\son[a-z0-9_-]+\s*=", markup, re.IGNORECASE):
        return False
    if re.search(
        r"<(?:a|form|iframe|object|embed|base|link|img|video|audio|svg|math)\b",
        markup,
        re.IGNORECASE,
    ):
        return False
    if re.search(
        r"\s(?:href|src|srcset|action|formaction)\s*=", markup, re.IGNORECASE
    ):
        return False
    if re.search(r"<meta\b[^>]*\bhttp-equiv\s*=", markup, re.IGNORECASE):
        return False

    expected_scripts, expected_css = _trusted_roadmap_runtime_surface()
    actual_scripts: dict[str, str] = {}
    json_script_ids: set[str] = set()
    for match in re.finditer(
        r"<script\b([^>]*)>([\s\S]*?)</script\s*>", content, re.IGNORECASE
    ):
        attrs, source = match.groups()

        def attr(name: str) -> str:
            value = re.search(
                rf"\b{re.escape(name)}\s*=\s*([\"'])(.*?)\1",
                attrs,
                re.IGNORECASE,
            )
            return value.group(2) if value else ""

        if attr("src"):
            return False
        if attr("type").lower() == "application/json":
            script_id = attr("id")
            if script_id not in _ROADMAP_JSON_SCRIPT_IDS or script_id in json_script_ids:
                return False
            json_script_ids.add(script_id)
            continue
        runtime_id = attr("data-roadmap-runtime")
        if runtime_id not in expected_scripts or runtime_id in actual_scripts:
            return False
        actual_scripts[runtime_id] = source.strip()

    if json_script_ids != _ROADMAP_JSON_SCRIPT_IDS or actual_scripts != expected_scripts:
        return False
    styles = re.findall(r"<style\b[^>]*>([\s\S]*?)</style\s*>", content, re.IGNORECASE)
    return len(styles) == 1 and styles[0].strip() == expected_css.strip()


def roadmap_layout_id_for_html_artifact(abs_file: Path, size: int) -> str:
    """Return the trusted Roadmap layout id, or an empty string when invalid."""
    if abs_file.suffix.lower() not in {".html", ".htm"}:
        return ""
    if size < 0 or size > _HTML_ARTIFACT_METADATA_LIMIT:
        return ""
    try:
        content = abs_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""

    def meta(name: str) -> str:
        pattern = re.compile(
            rf"<meta\b(?=[^>]*\bname=[\"']{re.escape(name)}[\"'])(?=[^>]*\bcontent=[\"']([^\"']*)[\"'])[^>]*>",
            re.IGNORECASE,
        )
        match = pattern.search(content)
        return match.group(1).strip() if match else ""

    layout_id = meta("box-agent-artifact-layout-id")
    if layout_id != _ROADMAP_LAYOUT_ID or len(layout_id) > 128:
        return ""
    if meta("generator") != _ROADMAP_GENERATOR:
        return ""
    try:
        if not _has_trusted_roadmap_runtime_surface(content):
            return ""
    except (OSError, UnicodeError):
        return ""
    sources = re.findall(
        r"<script\b(?=[^>]*\bid=[\"']deck-document[\"'])"
        r"(?=[^>]*\btype=[\"']application/json[\"'])[^>]*>"
        r"([\s\S]*?)</script\s*>",
        content,
        re.IGNORECASE,
    )
    if len(sources) != 1:
        return ""
    try:
        _roadmap_spec_validator().validate(json.loads(sources[0]))
    except Exception:
        return ""
    return layout_id
