"""Filesystem-derived checkpoint state for controlled presentations."""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from ..artifacts import OUTPUT_SUBDIR
from ..loop_guards import CompletionGate
from .presentation_contract import (
    CHECKPOINT_MARKER,
    RESEARCH_MODE_OPTION,
    WORKFLOW_KIND,
)


_CONTROLLED_PPTX_SCRIPTS_DIR: Final = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "document-skills"
    / "pptx"
    / "scripts"
)


def _controlled_pptx_command(script_name: str, arguments: str) -> str:
    script_path = shlex.quote(str(_CONTROLLED_PPTX_SCRIPTS_DIR / script_name))
    return f"${{BOX_AGENT_NODE:-node}} {script_path} {arguments}"


CONTROLLED_PRESENTATION_CHECKPOINT_MARKER: Final = CHECKPOINT_MARKER

_SCAFFOLD_PLACEHOLDERS: Final[tuple[str, ...]] = (
    "输入演示标题",
    "输入页面标题",
    "输入数据结论",
    "输入流程标题",
    "在这里写下最需要被记住的结论",
    "品牌项目 A（待补充）",
)

_CONTROLLED_PRESENTATION_REPORTS: Final[tuple[str, ...]] = (
    "outline_check.json",
    "deck_contract.json",
    "deck_spec.json",
    "truth_check.json",
    "image_manifest.json",
    "html_self_check.json",
    "runtime_probe.json",
)
_RESEARCH_FALLBACK_MIN_MARKDOWN_FILES: Final = 3


def _newest_file(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime_ns)


def _deck_has_scaffold_placeholders(deck_path: Path) -> bool:
    try:
        text = deck_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(placeholder in text for placeholder in _SCAFFOLD_PLACEHOLDERS)


def _report_is_ok(report_path: Path) -> bool:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("ok") is True


def _report_state(
    report_path: Path,
    dependencies: tuple[Path, ...] = (),
) -> str:
    """Return missing, invalid, failed, ok, or stale_* for one QA report."""
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return "missing"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "invalid"
    if not isinstance(payload, dict):
        state = "invalid"
    else:
        state = "ok" if payload.get("ok") is True else "failed"
    try:
        report_mtime = report_path.stat().st_mtime_ns
        if any(
            dependency.is_file()
            and dependency.stat().st_mtime_ns > report_mtime
            for dependency in dependencies
        ):
            return f"stale_{state}"
    except OSError:
        pass
    return state


def _report_warning_count(report_path: Path) -> int:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        return len(warnings)
    if isinstance(warnings, int) and warnings > 0:
        return warnings
    return 0


def _advisory_report_warning_count(report_path: Path) -> int:
    """Count warnings plus legacy hard issues from one advisory report."""
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    count = _report_warning_count(report_path)
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = payload.get("errors")
    count += len([issue for issue in raw_issues or [] if isinstance(issue, str)])
    # A current legacy ``ok:false`` truth report is itself advisory evidence,
    # even when the old writer omitted its issue payload.
    return max(1, count)


def _research_fallback_available(research_files: tuple[Path, ...]) -> bool:
    """Return whether bounded research work is enough to continue safely."""
    markdown_count = sum(path.suffix.casefold() == ".md" for path in research_files)
    report_attempted = any(
        path.name.endswith("_research_check.json")
        for path in research_files
    )
    return (
        report_attempted
        or markdown_count >= _RESEARCH_FALLBACK_MIN_MARKDOWN_FILES
    )


def _presentation_research_artifacts(workspace_dir: str | Path) -> tuple[bool, tuple[Path, ...]]:
    """Return whether a fresh validated deep-research handoff is complete."""
    workspace_root = Path(workspace_dir)
    # Presentation tools execute from the artifact root (``output/``), so the
    # canonical research handoff is ``output/research``.  Older sessions and
    # direct callers may still have written ``research`` beside ``output``;
    # retain that location as a read-only compatibility fallback.
    research_roots = (
        workspace_root / OUTPUT_SUBDIR / "research",
        workspace_root / "research",
    )
    research_root = next(
        (candidate for candidate in research_roots if candidate.is_dir()),
        None,
    )
    if research_root is None:
        return (False, ())

    def non_empty(paths: Iterable[Path]) -> list[Path]:
        found = []
        for candidate in paths:
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    found.append(candidate)
            except OSError:
                continue
        return sorted(found)

    observed = non_empty(
        [
            *research_root.rglob("*.md"),
            *research_root.glob("*_evidence.json"),
        ]
    )
    report_paths = non_empty(research_root.rglob("*_research_check.json"))
    for report_path in sorted(
        report_paths,
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    ):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            continue
        if payload.get("validator") != "research-synthesis":
            continue
        route = payload.get("route")
        topic = payload.get("topic")
        min_dimensions = payload.get("min_dimensions")
        dimension_count = payload.get("dimension_count")
        evidence_schema_version = payload.get("evidence_schema_version")
        evidence_file_value = payload.get("evidence_file")
        verified_evidence_count = payload.get("verified_evidence_count")
        verified_evidence = payload.get("verified_evidence")
        if (
            route not in {"A", "B"}
            or not isinstance(topic, str)
            or not topic.strip()
            or not isinstance(min_dimensions, int)
            or min_dimensions < 3
            or not isinstance(dimension_count, int)
            or dimension_count < min_dimensions
            or evidence_schema_version != 1
            or not isinstance(evidence_file_value, str)
            or not isinstance(verified_evidence_count, int)
            or verified_evidence_count < 1
            or not isinstance(verified_evidence, list)
            or len(verified_evidence) != verified_evidence_count
        ):
            continue
        if any(
            not isinstance(item, dict)
            or item.get("status") != "verified"
            or not isinstance(item.get("entity"), str)
            or not item["entity"].strip()
            or not isinstance(item.get("claim"), str)
            or not item["claim"].strip()
            or not isinstance(item.get("source_url"), str)
            or not item["source_url"].startswith(("http://", "https://"))
            or not isinstance(item.get("canonical"), str)
            or not item["canonical"].strip()
            for item in verified_evidence
        ):
            continue
        evidence_file = research_root / f"{topic}_evidence.json"
        try:
            reported_evidence_file = Path(evidence_file_value).resolve()
            if (
                not evidence_file.is_file()
                or reported_evidence_file != evidence_file.resolve()
            ):
                continue
        except OSError:
            continue
        dimensions = non_empty(research_root.glob(f"{topic}_dim*.md"))
        wide = non_empty(research_root.glob(f"{topic}_wide*.md"))
        cross_verification = non_empty(
            [research_root / f"{topic}_cross_verification.md"]
        )
        insights = non_empty([research_root / f"{topic}_insight.md"])
        if (
            len(dimensions) < min_dimensions
            or (route == "A" and not wide)
            or not cross_verification
            or not insights
        ):
            continue
        handoff_files = tuple(
            dict.fromkeys(
                [
                    *wide,
                    *dimensions,
                    *cross_verification,
                    *insights,
                    evidence_file,
                    report_path,
                ]
            )
        )
        try:
            report_mtime = report_path.stat().st_mtime_ns
            if any(path.stat().st_mtime_ns > report_mtime for path in handoff_files[:-1]):
                continue
        except OSError:
            continue
        return (True, handoff_files)
    return (False, tuple(dict.fromkeys([*observed, *report_paths])))


def _verified_research_evidence(research_files: tuple[Path, ...]) -> list[str]:
    """Return only validator-approved canonical facts for outline binding."""
    report_path = next(
        (
            path
            for path in research_files
            if path.name.endswith("_research_check.json")
        ),
        None,
    )
    if report_path is None:
        return []
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    evidence = payload.get("verified_evidence") if isinstance(payload, dict) else None
    if not isinstance(evidence, list):
        return []
    return [
        item["canonical"].strip()
        for item in evidence
        if isinstance(item, dict)
        and item.get("status") == "verified"
        and isinstance(item.get("canonical"), str)
        and item["canonical"].strip()
    ]


def _manifest_generation_progress(
    manifest_path: Path,
    artifact_root: Path,
) -> tuple[int, int, int, tuple[str, ...]]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (0, 0, 0, ())
    image_plan = payload.get("image_plan") if isinstance(payload, dict) else None
    if not isinstance(image_plan, list):
        return (0, 0, 0, ())
    expected = 0
    ready = 0
    status_ready = 0
    ready_paths: list[str] = []
    for entry in image_plan:
        if not isinstance(entry, dict):
            continue
        decision = entry.get("decision")
        if decision not in {"generate", "use_existing"}:
            continue
        if decision == "generate":
            expected += 1
        output_path = entry.get("output_path")
        if not isinstance(output_path, str) or not output_path.strip():
            continue
        path = artifact_root / output_path
        try:
            if path.is_file() and path.stat().st_size > 0:
                ready_paths.append(output_path.strip())
                if decision != "generate":
                    continue
                ready += 1
                status = str(entry.get("status") or "").strip().lower()
                if status in {
                    "generated",
                    "ready",
                    "complete",
                    "completed",
                    "reused",
                    "fixed",
                }:
                    status_ready += 1
        except OSError:
            continue
    return (ready, expected, status_ready, tuple(ready_paths))


def _missing_artifact_references(
    artifact_path: Path,
    references: tuple[str, ...] | list[str],
) -> list[str]:
    if not references:
        return []
    try:
        text = artifact_path.read_text(encoding="utf-8")
    except OSError:
        return list(references)
    return [reference for reference in references if reference not in text]


def _json_field_shape(value: object) -> object:
    """Return a compact JSON-compatible field shape without scaffold prose."""
    if isinstance(value, dict):
        return {str(key): _json_field_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_field_shape(value[0])] if value else []
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if value is None:
        return None
    return "<string>"


def _outline_title_prop_path(layout_id: object, props: dict[str, object]) -> str | None:
    """Return the visible heading prop that must preserve the outline title."""
    if layout_id == "statement-focus-v1" and "statement" in props:
        return "statement"
    if "title" in props:
        return "title"
    return None


def _numeric_literals(*values: object) -> list[str]:
    """Return digit-bearing literals explicitly present in page source text."""
    source = json.dumps(values, ensure_ascii=False)
    return list(dict.fromkeys(re.findall(r"\d+(?:[.,]\d+)?(?:[%％])?", source)))


_MISSING_PRIVATE_FACT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:未提供|未给出|待补充|待确认|缺失|未知|"
    r"not\s+provided|not\s+supplied|missing|unknown|tbd)",
    re.IGNORECASE,
)


def _missing_fact_evidence(value: object) -> list[str]:
    """Return exact outline evidence that discloses unavailable private facts."""
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
        and _MISSING_PRIVATE_FACT_RE.search(item)
    ]


def _content_patch_input(
    outline_path: Path | None,
    deck_path: Path,
    generated_paths: tuple[str, ...],
) -> str | None:
    """Build the complete compact input needed for one all-slide content patch."""
    if outline_path is None:
        return None
    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    outline_slides = outline.get("slides") if isinstance(outline, dict) else None
    deck_slides = deck.get("slides") if isinstance(deck, dict) else None
    if not isinstance(outline_slides, list) or not isinstance(deck_slides, list):
        return None
    source_mode = str(outline.get("source_mode") or "").strip().lower()
    user_provided_source = source_mode == "user_provided"

    media_bindings: list[dict[str, object]] = []
    manifest_path = deck_path.parent / "assets" / "generated" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = None
    image_plan = manifest.get("image_plan") if isinstance(manifest, dict) else None
    if isinstance(image_plan, list):
        ready_path_set = set(generated_paths)
        media_bindings = [
            {
                "slide_id": entry.get("slide_id"),
                "prop_path": entry.get("prop_path"),
                "path": entry.get("output_path"),
                "origin": "uploaded"
                if entry.get("decision") == "use_existing"
                else "generated",
                "alt_policy": (
                    "Describe supplied asset accurately"
                    if entry.get("decision") == "use_existing"
                    else "Label product/project concepts as AI concept visuals, not documentary screenshots"
                ),
            }
            for entry in image_plan
            if isinstance(entry, dict)
            and entry.get("output_path") in ready_path_set
        ]

    pages: list[dict[str, object]] = []
    for index, deck_slide in enumerate(deck_slides):
        if not isinstance(deck_slide, dict):
            continue
        source_page = deck_slide.get("source_outline_page")
        outline_index = source_page - 1 if isinstance(source_page, int) else index
        if not (0 <= outline_index < len(outline_slides)):
            return None
        outline_slide = outline_slides[outline_index]
        if not isinstance(outline_slide, dict):
            return None
        props = deck_slide.get("props")
        props_dict = props if isinstance(props, dict) else {}
        missing_fact_evidence = _missing_fact_evidence(
            outline_slide.get("evidence")
        )
        structural_numeric_literals = (
            [str(len(deck_slides))] if outline_index == 0 else []
        )
        pages.append(
            {
                "slide_id": deck_slide.get("id") or f"slide-{index + 1:02d}",
                "layout_id": deck_slide.get("layout_id"),
                "source_outline_page": outline_index + 1,
                "title": outline_slide.get("title"),
                "title_prop_path": _outline_title_prop_path(
                    deck_slide.get("layout_id"),
                    props_dict,
                ),
                "message": outline_slide.get("message"),
                "bullets": outline_slide.get("bullets"),
                "evidence": outline_slide.get("evidence"),
                "disclosure_required": bool(missing_fact_evidence),
                "disclosure_evidence": missing_fact_evidence,
                # Public research remains bound to its evidence ledger. In a
                # user-provided outline, exact quantities in the page copy came
                # directly from the user and are valid even without URL evidence.
                "allowed_numeric_literals": _numeric_literals(
                    outline_slide.get("evidence"),
                    outline_slide.get("message") if user_provided_source else None,
                    outline_slide.get("bullets") if user_provided_source else None,
                ),
                # The page count is a structural deck fact, not researched topic
                # evidence. It is safe only in cover metadata explicitly labelled
                # as a page/slide count.
                "structural_numeric_literals": structural_numeric_literals,
                "prop_shape": _json_field_shape(props_dict),
                "props_template": props_dict,
            }
        )
    if not pages:
        return None
    truth_contract = deck.get("truth_contract")
    compact_truth = None
    if isinstance(truth_contract, dict):
        compact_truth = {
            key: truth_contract.get(key)
            for key in ("source_facts", "research_facts", "assumptions")
            if isinstance(truth_contract.get(key), list)
        }
    return json.dumps(
        {
            "patch_format": (
                'Top level must be {"slides":{...}}. Nest every supplied '
                'slide_id under slides, for example '
                '{"slides":{"slide-01":{"props":{...}}}}; never put '
                'slide-01, slide-02, etc. at the top level.'
            ),
            "ready_media_paths": list(generated_paths),
            "ready_media_bindings": media_bindings,
            "truth_contract": compact_truth,
            "pages": pages,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _scaffold_input(outline_path: Path) -> str | None:
    """Return registered ids plus compact page intent for one scaffold call."""
    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "document-skills"
        / "pptx"
        / "layouts"
        / "manifest.json"
    )
    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    outline_slides = outline.get("slides") if isinstance(outline, dict) else None
    themes = manifest.get("themes") if isinstance(manifest, dict) else None
    layouts = manifest.get("layouts") if isinstance(manifest, dict) else None
    if (
        not isinstance(outline_slides, list)
        or not isinstance(themes, list)
        or not isinstance(layouts, list)
    ):
        return None

    theme_ids = [
        theme.get("id")
        for theme in themes
        if isinstance(theme, dict) and isinstance(theme.get("id"), str)
    ]
    registered_layouts = [
        {
            "id": layout.get("id"),
            "label": layout.get("label"),
            "roles": layout.get("roles"),
            "content_shape": layout.get("contentShape"),
            "density": layout.get("density"),
        }
        for layout in layouts
        if isinstance(layout, dict) and isinstance(layout.get("id"), str)
    ]
    layout_ids = [layout["id"] for layout in registered_layouts]
    pages = [
        {
            "page": slide.get("page"),
            "title": slide.get("title"),
            "message": slide.get("message"),
            "layout_intent": slide.get("layout"),
            "visual_intent": slide.get("visual"),
            "evidence": slide.get("evidence"),
        }
        for slide in outline_slides
        if isinstance(slide, dict)
    ]
    if not theme_ids or not layout_ids or not pages:
        return None
    return json.dumps(
        {
            "default_theme_id": manifest.get("default_theme_id"),
            "registered_theme_ids": theme_ids,
            "registered_layout_ids": layout_ids,
            "registered_layouts": registered_layouts,
            "pages": pages,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _image_generation_input(
    manifest_path: Path,
    artifact_root: Path,
    outline_path: Path | None,
    deck_path: Path,
) -> str | None:
    """Return every missing planned image with enough context to generate it."""
    layout_manifest_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "document-skills"
        / "pptx"
        / "layouts"
        / "manifest.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        layout_manifest = json.loads(layout_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or not isinstance(deck, dict):
        return None
    image_plan = manifest.get("image_plan")
    if not isinstance(image_plan, list):
        return None

    outline_pages: dict[int, dict[str, object]] = {}
    if outline_path is not None:
        try:
            outline = json.loads(outline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            outline = None
        if isinstance(outline, dict) and isinstance(outline.get("slides"), list):
            outline_pages = {
                slide.get("page"): slide
                for slide in outline["slides"]
                if isinstance(slide, dict) and isinstance(slide.get("page"), int)
            }

    layouts = layout_manifest.get("layouts") if isinstance(layout_manifest, dict) else []
    layout_by_id = {
        layout.get("id"): layout
        for layout in layouts or []
        if isinstance(layout, dict) and isinstance(layout.get("id"), str)
    }
    themes = layout_manifest.get("themes") if isinstance(layout_manifest, dict) else []
    theme = next(
        (
            item
            for item in themes or []
            if isinstance(item, dict) and item.get("id") == deck.get("theme_id")
        ),
        None,
    )

    pending: list[dict[str, object]] = []
    for entry in image_plan:
        if not isinstance(entry, dict) or entry.get("decision") != "generate":
            continue
        output_path = entry.get("output_path")
        if not isinstance(output_path, str) or not output_path.strip():
            continue
        try:
            if (artifact_root / output_path).is_file():
                continue
        except OSError:
            pass
        page = entry.get("slide")
        outline_slide = outline_pages.get(page) if isinstance(page, int) else None
        layout = layout_by_id.get(entry.get("layout_id"))
        preferred_ratio = None
        if isinstance(layout, dict):
            media_slots = layout.get("mediaSlots")
            slots = media_slots.get("slots") if isinstance(media_slots, dict) else None
            if isinstance(slots, list):
                slot = next(
                    (
                        item
                        for item in slots
                        if isinstance(item, dict) and item.get("id") == entry.get("slot")
                    ),
                    None,
                )
                if isinstance(slot, dict):
                    preferred_ratio = slot.get("preferredRatio")
        pending.append(
            {
                "slide": page,
                "slide_id": entry.get("slide_id"),
                "layout_id": entry.get("layout_id"),
                "slot": entry.get("slot"),
                "prop_path": entry.get("prop_path"),
                "output_path": output_path.strip(),
                "preferred_ratio": preferred_ratio,
                "existing_prompt": entry.get("prompt"),
                "title": outline_slide.get("title") if outline_slide else None,
                "message": outline_slide.get("message") if outline_slide else None,
                "visual_intent": outline_slide.get("visual") if outline_slide else None,
            }
        )
    if not pending:
        return None
    return json.dumps(
        {
            "deck_title": deck.get("title"),
            "theme_id": deck.get("theme_id"),
            "theme_style": theme.get("style") if isinstance(theme, dict) else None,
            "theme_palette": theme.get("palette") if isinstance(theme, dict) else None,
            "watermark": False,
            "negative_prompt": "embedded text, watermark, logo, blurry output",
            "entries": pending,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _qa_repair_input(
    report_path: Path,
    deck_path: Path,
    outline_path: Path | None,
) -> str | None:
    """Return fresh report issues with the exact affected slide context."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(report, dict) or not isinstance(deck, dict):
        return None
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = report.get("errors")
    issues = [issue for issue in raw_issues or [] if isinstance(issue, str)]
    if not issues:
        return None

    affected_ids = {
        match.group(1)
        for issue in issues
        for match in re.finditer(r"slides\.(slide-[A-Za-z0-9_-]+)", issue)
    }
    deck_slides = deck.get("slides")
    if not affected_ids or not isinstance(deck_slides, list):
        return None

    outline_slides: list[object] = []
    if outline_path is not None:
        try:
            outline = json.loads(outline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            outline = None
        if isinstance(outline, dict) and isinstance(outline.get("slides"), list):
            outline_slides = outline["slides"]

    affected_slides: list[dict[str, object]] = []
    for index, slide in enumerate(deck_slides):
        if not isinstance(slide, dict) or slide.get("id") not in affected_ids:
            continue
        source_page = slide.get("source_outline_page")
        outline_index = source_page - 1 if isinstance(source_page, int) else index
        outline_slide = (
            outline_slides[outline_index]
            if 0 <= outline_index < len(outline_slides)
            and isinstance(outline_slides[outline_index], dict)
            else None
        )
        affected_slides.append(
            {
                "slide_id": slide.get("id"),
                "source_outline_page": outline_index + 1,
                "current_props": slide.get("props"),
                "protected_title_prop_path": _outline_title_prop_path(
                    slide.get("layout_id"),
                    (
                        slide.get("props")
                        if isinstance(slide.get("props"), dict)
                        else {}
                    ),
                ),
                "outline": (
                    {
                        "title": outline_slide.get("title"),
                        "message": outline_slide.get("message"),
                        "bullets": outline_slide.get("bullets"),
                        "evidence": outline_slide.get("evidence"),
                    }
                    if outline_slide is not None
                    else None
                ),
            }
        )
    if not affected_slides:
        return None

    truth_contract = deck.get("truth_contract")
    compact_truth = None
    if isinstance(truth_contract, dict):
        compact_truth = {
            key: truth_contract.get(key)
            for key in ("source_facts", "research_facts", "assumptions")
            if isinstance(truth_contract.get(key), list)
        }
    return json.dumps(
        {
            "report": report_path.name,
            "issues": issues,
            "affected_slides": affected_slides,
            "truth_contract": compact_truth,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _outline_repair_input(
    report_path: Path,
    outline_path: Path,
    research_files: tuple[Path, ...] = (),
) -> str | None:
    """Return one self-contained input for repairing a failed outline.

    A failing validator writes the useful issue list to JSON while the bash tool
    itself commonly reports only exit code 1.  Embedding both that list and the
    current outline prevents repeated report/file/reference reads and gives the
    model one exact mutation target.
    """
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(report, dict) or not isinstance(outline, dict):
        return None
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = report.get("errors")
    issues = [issue for issue in raw_issues or [] if isinstance(issue, str)]
    if not issues:
        return None
    # Match the same conservative URL surface used by the runtime provenance
    # ledger.  In particular, do not absorb Markdown closing delimiters into a
    # URL, otherwise a valid handoff link can be mislabeled as unsupported.
    url_pattern = re.compile(
        r"https?://[^\s<>\"'\]\[{}()|]+",
        re.IGNORECASE,
    )
    allowed_research_urls: set[str] = set()
    for research_file in research_files:
        if research_file.suffix.casefold() != ".md":
            continue
        try:
            research_text = research_file.read_text(encoding="utf-8")
        except OSError:
            continue
        allowed_research_urls.update(
            match.rstrip(".,;:!?，。；：！？")
            for match in url_pattern.findall(research_text)
        )
    current_outline_urls = {
        match.rstrip(".,;:!?，。；：！？")
        for match in url_pattern.findall(
            json.dumps(outline, ensure_ascii=False, separators=(",", ":"))
        )
    }
    return json.dumps(
        {
            "report": report_path.name,
            "issues": issues,
            "allowed_research_urls": sorted(allowed_research_urls),
            "unsupported_evidence_urls": sorted(
                current_outline_urls - allowed_research_urls
            ),
            "current_outline": outline,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_checkpoint_text(
    workspace_dir: str | None,
    research_mode: str | None,
    *,
    research_fallback_allowed: bool = False,
    research_fallback_reason: str | None = None,
    research_attempt_summary: dict[str, int] | None = None,
) -> str | None:
    """Return an authoritative next-stage checkpoint for controlled decks.

    The checkpoint intentionally uses only filesystem evidence. It is safe to
    recompute before every model request; core keeps one refreshed copy as the
    latest instruction while emitting a new checkpoint event only when the
    filesystem-backed stage changes.
    """
    if not workspace_dir:
        return None

    output_root = Path(workspace_dir) / OUTPUT_SUBDIR
    research_required = research_mode == "deep"
    research_ready, research_files = _presentation_research_artifacts(workspace_dir)
    verified_research_evidence = (
        _verified_research_evidence(research_files) if research_ready else []
    )
    research_fallback = (
        research_required
        and not research_ready
        and (
            research_fallback_allowed
            or _research_fallback_available(research_files)
        )
    )
    fallback_reason = (
        research_fallback_reason
        if research_fallback
        else None
    )
    if research_fallback and fallback_reason is None:
        fallback_reason = "research_artifacts_incomplete_or_validation_failed"
    fallback_messages = {
        "research_sources_unavailable": (
            "Search or direct-read rounds returned only failures or empty results, "
            "so no research report could be validated."
        ),
        "research_round_limit_reached_without_validated_report": (
            "The bounded research rounds completed without producing a validated "
            "research report."
        ),
        "research_artifacts_incomplete_or_validation_failed": (
            "Research artifacts were attempted, but the required handoff or its "
            "validation report was incomplete or unsuccessful."
        ),
    }
    fallback_message = (
        fallback_messages.get(
            fallback_reason,
            "No validated research report was available when the workflow continued.",
        )
        if research_fallback
        else None
    )
    outline_path = _newest_file(list(output_root.rglob("outline.json")))
    deck_path = _newest_file(list(output_root.rglob("deck.json")))
    html_path = _newest_file(
        [
            path
            for path in output_root.rglob("*.html")
            if "qa" not in path.parts
        ]
    )
    try:
        html_current = html_path is not None and (
            deck_path is None
            or html_path.stat().st_mtime_ns >= deck_path.stat().st_mtime_ns
        )
    except OSError:
        html_current = False
    artifact_root = deck_path.parent if deck_path is not None else (
        html_path.parent if html_path is not None else (
            outline_path.parent if outline_path is not None else output_root
        )
    )
    patch_path = artifact_root / "deck.patch.json"
    manifest_path = artifact_root / "assets" / "generated" / "manifest.json"
    (
        generated_ready,
        generated_expected,
        generated_status_ready,
        generated_paths,
    ) = _manifest_generation_progress(
        manifest_path,
        artifact_root,
    )
    report_dir = artifact_root / "qa"
    research_report_path = next(
        (
            path
            for path in research_files
            if research_ready and path.name.endswith("_research_check.json")
        ),
        None,
    )
    research_report_argument = (
        f" --research-report {shlex.quote(str(research_report_path))}"
        if research_report_path is not None
        else ""
    )
    validate_outline_command = _controlled_pptx_command(
        "validate_outline.js",
        (
            "outline.json"
            f"{research_report_argument}"
            " --report qa/outline_check.json"
        ),
    )
    apply_patch_command = _controlled_pptx_command(
        "apply_deck_patch.js",
        "deck.json deck.patch.json",
    )
    finalize_command = _controlled_pptx_command(
        "finalize_controlled_deck.js",
        "deck.json --out index.html",
    )
    sync_image_status_command = _controlled_pptx_command(
        "sync_image_manifest_status.js",
        "assets/generated/manifest.json",
    )
    generated_files = tuple(artifact_root / path for path in generated_paths)
    report_dependencies: dict[str, tuple[Path, ...]] = {
        "outline_check.json": tuple(
            path
            for path in (
                outline_path,
                *(research_files if research_required else ()),
            )
            if path
        ),
        "deck_contract.json": (),
        "deck_spec.json": tuple(
            path for path in (deck_path, outline_path) if path
        ),
        "truth_check.json": tuple(path for path in (deck_path,) if path),
        "image_manifest.json": tuple(
            path
            for path in (deck_path, manifest_path, *generated_files)
            if path is not None and path.is_file()
        ),
        "html_self_check.json": tuple(
            path for path in (html_path, deck_path) if path
        ),
        "runtime_probe.json": tuple(
            path for path in (html_path, deck_path) if path
        ),
    }
    report_states = {
        name: _report_state(
            report_dir / name,
            report_dependencies.get(name, ()),
        )
        for name in _CONTROLLED_PRESENTATION_REPORTS
    }
    truth_report_advisory = report_states["truth_check.json"] == "failed"
    if truth_report_advisory:
        # Source/truth QA is advisory. Missing, invalid, and stale reports still
        # need the finalizer to refresh them, but a current legacy ``ok:false``
        # report must not send the model into a content-repair loop.
        report_states["truth_check.json"] = "ok"
    report_status = {
        name: state == "ok" for name, state in report_states.items()
    }
    qa_ready = sum(report_status.values())
    qa_warnings = sum(
        (
            _advisory_report_warning_count(report_dir / name)
            if name == "truth_check.json" and truth_report_advisory
            else _report_warning_count(report_dir / name)
        )
        for name in _CONTROLLED_PRESENTATION_REPORTS
    )

    outline_report_path = report_dir / "outline_check.json"
    outline_repair_input = (
        _outline_repair_input(
            outline_report_path,
            outline_path,
            research_files if research_required else (),
        )
        if outline_path is not None
        and report_states["outline_check.json"] == "failed"
        else None
    )
    if (
        research_required
        and not research_ready
        and not research_fallback
        and outline_path is None
        and deck_path is None
        and html_path is None
    ):
        stage = "research"
        next_action = (
            "This short factual presentation brief requires the preloaded "
            "research-synthesis workflow before outline authoring. Choose Route A "
            "for a broad landscape or Route B for a bounded topic, run the skill's "
            "coarse-to-fine searches, and preserve the full useful search evidence "
            "under research/. Do not replace that workflow with an ad-hoc four-query "
            "scan. Consume each result set before the next batch; every later query "
            "must name a still-uncovered slide-relevant dimension, conflict, or "
            "first-party source instead of lightly rephrasing an already-run "
            "entity/fact query. An empty AuthLevel or site:-filtered result is not "
            "permission to repeat the same intent without the filter. For a known "
            "exact URL, use an actually available direct browser tool; in officev3 "
            "use standalone Playwright MCP rather than browser-gateway "
            "source_preference:playwright, or use gateway auto/browser_connector. "
            "Do not create or validate outline.json yet. The checkpoint "
            "advances only after research/ contains at least three distinct "
            "dimension files, the route's cross-verification and insight files, "
            "and a fresh successful research/qa/*_research_check.json written by "
            "validate_research_artifacts.py --report. Route A must also include "
            "wide exploration. If an early "
            "outline already exists, preserve it; update it from the completed "
            "research in the next stage instead of deleting or duplicating it."
        )
    elif (deck_path is not None or html_path is not None) and outline_path is None:
        stage = "outline_backfill"
        next_action = (
            "The existing deck predates its required narrative provenance. Do not "
            "recreate or rewrite deck.json/index.html. Derive one outline.json from "
            "the existing ordered slides and their evidence, then run `"
            f"{validate_outline_command}`. This is a provenance backfill, not a "
            "new authoring pass."
        )
    elif (
        (deck_path is not None or html_path is not None)
        and outline_repair_input is not None
    ):
        stage = "outline_repair"
        next_action = (
            "REPAIR_INPUT below contains the complete current outline and the fresh "
            "validator issues. Do not reread outline.json, the report, outline.md, or "
            "run another command. Your very next tool call must write one corrected "
            "outline.json, preserving supported content and changing only what the "
            "issues require. Use canonical top-level keys deck_goal, audience, "
            "source_mode, storyline, slides and canonical per-slide keys page, title, "
            "message, bullets, layout, visual, evidence. Do not recreate or rewrite "
            "the existing deck or HTML. Treat unsupported_evidence_urls in "
            "REPAIR_INPUT as advisory provenance gaps. Do not invent or relabel a "
            "source, but do not block outline repair: omit an optional unsupported "
            "claim or use 暂无可验证公开数据 for a required fact. The refreshed "
            "filesystem checkpoint will "
            "validate the repaired outline next."
        )
    elif (
        (deck_path is not None or html_path is not None)
        and report_states["outline_check.json"] != "ok"
    ):
        stage = "outline_qa"
        next_action = (
            "Validate the existing outline.json with `"
            f"{validate_outline_command}` and repair only reported outline issues. Do not "
            "recreate or rewrite the existing deck or HTML."
        )
    elif html_path is not None and html_current:
        missing_reports = [
            name for name, ok in report_status.items() if not ok
        ]
        if not missing_reports:
            stage = "complete"
            next_action = (
                "All required QA reports are ok. Stop calling tools and return "
                "the editable HTML deliverable to the user. "
                f"The reports contain {qa_warnings} warning(s); state that count "
                "as pass-with-warnings in Limitations and do not call the run "
                "clean, all-green, or warning-free when the count is non-zero."
            )
        else:
            stage = "qa"
            next_action = (
                "Keep the existing HTML and run or repair only the missing/failed "
                f"QA checks: {', '.join(missing_reports)}. Do not restart authoring."
            )
    elif deck_path is None:
        if outline_path is None:
            stage = "outline"
            next_action = (
                (
                    "Research QA is complete. Do not call web_search or any browser "
                    "tool again, do not reread the research QA report or outline.md, "
                    "and do not list/check the filesystem. If the handoff contents "
                    "are not already present in the current model context, read the "
                    "completed Markdown handoff files named in RESEARCH_INPUT in one "
                    "parallel batch for narrative context; otherwise skip reading. "
                    "For factual evidence, copy only the canonical strings in "
                    "RESEARCH_INPUT.verified_evidence. Never promote conflicting or "
                    "unverified prose from a Markdown file. Then your very next tool "
                    "call must write outline.json. "
                    if research_required and research_ready
                    else (
                        "Bounded research work is complete without a successful QA "
                        "report. Do not keep searching or retry research validation. "
                        "No research artifact has passed the entity/evidence gate, so "
                        "RESEARCH_INPUT contains no handoff files or verified evidence. "
                        "Do not use claims from unvalidated research files. Omit "
                        "optional unsupported claims and use 暂无可验证公开数据 for required "
                        "unavailable facts. Your very next tool call must write "
                        "outline.json so HTML delivery can continue. "
                        if research_required and research_fallback
                        else ""
                    )
                )
                + "Create exactly one concise outline.json before theme/layout "
                "selection using the canonical keys. Top level: deck_goal, "
                "audience, source_mode, storyline, slides. Every slide: page, "
                "title, message, bullets, layout, visual, evidence; bullets and "
                "evidence are arrays (use [] when evidence is empty); audience "
                "and storyline may each be a non-empty string or a non-empty "
                "array of strings. Do not use "
                "aliases such as goal, slide_no, layout_intent, or visual_intent. "
                "Set source_mode=public_authoritative_research after public "
                "research, give every page one distinct message and 2-5 "
                "substantive bullets, and do not spend multiple pages repeating "
                "the same fact. On a public-research page, every Arabic-number "
                "literal used in its title, message, or bullets must also appear "
                "verbatim in that page's evidence array; evidence is the fact "
                "ledger, so remove decorative/structural numbers that are not "
                "content claims. Every public-research page must include at least "
                "one evidence item unless it explicitly marks a required fact as "
                "unavailable; every non-empty item must include the actual http(s) "
                "source URL used for that claim. "
                "Treat AuthLevel as a ranking hint, not proof of authority: when "
                "a first-party domain is known, use a site:-constrained query, "
                "discard SEO-looking/mirror/unrelated results, and never label a "
                "source FIFA/IOC/official unless the returned URL belongs to that "
                "institution. When RESEARCH_INPUT.verified_evidence is non-empty, "
                "copy every evidence item exactly from that canonical list; another "
                "URL, claim, source type, or entity binding is a hard outline failure. "
                "Without a validated handoff. Do not invent the expected URL: omit "
                "the unsupported optional claim or use 暂无可验证公开数据 for a required "
                "field, then continue to HTML delivery. This "
                "schema is complete: do not read outline.md "
                "again, inspect/list themes or layouts, load a visual-template "
                "skill, or list the empty output directory until outline_check is "
                "ok. Assumptions may describe disclosed illustrative metrics or "
                "scenarios only. Never assume a company/project name, financing "
                "round or stage, founding date, team member/history/size, client, "
                "award, or other private identity fact; use 待补充 for a required "
                "private field and continue, or omit an optional gap. Do not ask for "
                "missing facts. For a public-research deck, omit nonessential gaps "
                "instead of planning visible 待补充 fields. Run `"
                f"{validate_outline_command}`, fix any issues, and stop before "
                "scaffolding so the validated narrative becomes the next checkpoint."
            )
        elif outline_repair_input is not None:
            stage = "outline_repair"
            next_action = (
                "REPAIR_INPUT below contains the complete current outline and the "
                "fresh validator issues. Do not reread outline.json, the report, "
                "outline.md, or run another command. Your very next tool call must "
                "write one corrected outline.json, preserving supported content and "
                "changing only what the issues require. Use canonical top-level keys "
                "deck_goal, audience, source_mode, storyline, slides and canonical "
                "per-slide keys page, title, message, bullets, layout, visual, "
                "evidence. Treat unsupported_evidence_urls in REPAIR_INPUT as "
                "advisory provenance gaps. Do not invent or relabel a source, but do "
                "not block outline repair: omit an optional unsupported claim or use "
                "暂无可验证公开数据 for a required fact. The "
                "refreshed filesystem checkpoint will validate it next; "
                "do not select layouts or scaffold deck.json yet."
            )
        elif report_states["outline_check.json"] != "ok":
            stage = "outline_qa"
            next_action = (
                "Validate the existing outline.json with `"
                f"{validate_outline_command}` and repair only its reported issues. Do not "
                "select layouts or scaffold deck.json until outline_check is ok."
            )
        else:
            stage = "scaffold"
            next_action = (
                "Use the validated outline.json as the page-by-page source of truth. "
                "SCAFFOLD_INPUT below already contains every registered theme/layout "
                "id and every page intent. Do not read outline.json, inspect/list the "
                "registry, or invent an id. Your very next tool call must invoke "
                "inspect_deck_contract.js once to create deck.json and its image "
                "manifest, passing `--outline outline.json --out deck.json`. The "
                "ordered plan may repeat layout "
                "ids; semantic fidelity is more important than forced variety. A "
                "qualitative page must not use chart-* or kpi-grid-v1 unless its "
                "outline evidence contains real quantities. For source_mode=user_provided, "
                "exact quantities in that page's message/bullets are evidence even when "
                "the external-link evidence array is empty. Choose layouts that can "
                "express each page's evidence without unresolved public-research "
                "placeholders. SCAFFOLD_INPUT.registered_layouts contains compact "
                "selection semantics; use project-case-study-v1 only for an actual "
                "source-backed project/case with proof metrics, not merely as a "
                "generic image-plus-text page. Choose --image-mode auto unless the brief activates "
                "creative_image_mode. Pass every --fact as an exact contiguous copy "
                "from the user's source; use --research-fact only for completed "
                "research not already present in the bound public-research outline, "
                "and --assumption only with explicit user permission. The scaffold "
                "automatically imports public outline evidence and writes "
                "source_outline_page. Do not paraphrase facts, infer dates, or "
                "repeat discovery calls."
            )
    else:
        has_placeholders = _deck_has_scaffold_placeholders(deck_path)
        patch_exists = patch_path.is_file() and patch_path.stat().st_size > 0
        missing_deck_media = _missing_artifact_references(
            deck_path,
            generated_paths,
        )
        missing_patch_media = (
            _missing_artifact_references(patch_path, missing_deck_media)
            if patch_exists
            else missing_deck_media
        )
        patch_needs_apply = False
        if patch_exists:
            try:
                patch_needs_apply = (
                    patch_path.stat().st_mtime_ns > deck_path.stat().st_mtime_ns
                    or has_placeholders
                )
            except OSError:
                patch_needs_apply = has_placeholders

        if generated_expected and generated_ready < generated_expected:
            stage = "images"
            next_action = (
                "IMAGE_INPUT below is complete and authoritative; do not read/list "
                "the manifest, deck, outline, generated-assets directory, or theme. "
                "Your very next tool call(s) must be one parallel batch of "
                "generate_image calls for only its entries. Use each exact "
                "output_path, watermark=false, the supplied palette/style and page "
                "intent, and avoid embedded text/logos. Do not edit manifest.json "
                "after generation; the next filesystem checkpoint will run the "
                "deterministic status sync. Never regenerate an existing file."
            )
        elif generated_expected and generated_status_ready < generated_expected:
            stage = "image_status_sync"
            next_action = (
                "All planned image files now exist; do not list the generated-assets "
                "directory, regenerate them, or edit/read manifest.json manually. "
                f"Run exactly `{sync_image_status_command}` once. The deterministic helper "
                "marks every existing planned asset ready without replacing the "
                "manifest, then the filesystem checkpoint will advance to the "
                "single all-slide content patch."
            )
        elif missing_deck_media and not patch_exists:
            stage = "content_patch"
            next_action = (
                "PATCH_INPUT below is complete and authoritative. Your very next "
                "tool call must write one deck.patch.json for all slides; do not "
                "call read_file, execute_code, bash, inspect/list, or any discovery "
                "tool first. The patch envelope must be exactly top-level "
                "{\"slides\":{...}}: nest each supplied slide_id under slides and "
                "never put slide-01/slide-02 keys at the top level. Include every ready "
                "generated media path in its declared prop or background. Keep "
                "slide N on outline page N: preserve its exact outline title and "
                "content anchors. On a quantitative page keep every allowed numeric "
                "literal with its matching label; values may be split across KPI/chart "
                "fields, so do not duplicate a full source sentence in every cell. On "
                "a qualitative page keep at least one exact atomic message/bullet "
                "fragment. Put the exact title in each page's "
                "declared title_prop_path. A digit-bearing value may appear only when "
                "that exact literal is listed in the page's allowed_numeric_literals; "
                "The cover may additionally use structural_numeric_literals only in "
                "a meta field explicitly labelled as a page/slide count. "
                "Do not translate Chinese number words into new Arabic metrics. Do "
                "not swap page topics, reuse the "
                "same evidence as the main point on more than two slides, or fill a "
                "qualitative page with dummy chart/KPI values. Use only "
                "scaffolded source facts plus explicitly user-authorized, visibly "
                "disclosed assumptions in truth_contract.assumptions. When a page "
                "has disclosure_required=true, visibly include its supplied "
                "disclosure_evidence in a subtitle, source, or note; never turn a "
                "missing team/company/project/funding fact into positive copy. Use "
                "待补充 only for required private fields, otherwise describe the "
                "capability or requirement neutrally. For public "
                "research, omit an unsupported optional claim rather than exposing "
                "待补充. Keep the "
                "existing manifest image_plan array schema; "
                "never replace manifest.json or rewrite deck.json directly."
            )
        elif missing_deck_media and missing_patch_media:
            stage = "media_patch"
            next_action = (
                "Add the ready generated media paths missing from deck.patch.json "
                f"({', '.join(missing_patch_media)}) to their declared props or "
                f"backgrounds, then apply that patch with `{apply_patch_command}`. Never use "
                "an ad-hoc script to rewrite deck.json."
            )
        elif missing_deck_media:
            stage = "apply_patch"
            next_action = (
                "The existing deck.patch.json already references the ready generated "
                f"media. Apply it now with `{apply_patch_command}`."
            )
        elif patch_needs_apply:
            stage = "apply_patch"
            next_action = (
                f"Run `{apply_patch_command}` now. Its compiler normalizes aliases and "
                "preserves advisory truth diagnostics. Do not reread/rewrite either "
                "file first; revise the patch only if that command returns an "
                "actionable structural error."
            )
        elif has_placeholders and not patch_exists:
            stage = "content_patch"
            next_action = (
                "PATCH_INPUT below is complete and authoritative. Your very next "
                "tool call must write one deck.patch.json for all slides; do not "
                "call read_file, execute_code, bash, inspect/list, or any discovery "
                "tool first. The patch envelope must be exactly top-level "
                "{\"slides\":{...}}: nest each supplied slide_id under slides and "
                "never put slide-01/slide-02 keys at the top level. Keep slide N on "
                "outline page N: preserve its exact outline title and content anchors. "
                "On a quantitative page keep every allowed numeric literal with its "
                "matching label; values may be split across KPI/chart fields, so do "
                "not duplicate a full source sentence in every cell. On a qualitative "
                "page keep at least one exact atomic message/bullet fragment. Put the "
                "exact title in each page's declared "
                "title_prop_path. A digit-bearing value may appear only when that "
                "exact literal is listed in the page's allowed_numeric_literals. "
                "The cover may additionally use structural_numeric_literals only in "
                "a meta field explicitly labelled as a page/slide count. Do "
                "not translate Chinese number words into new Arabic metrics. Do not "
                "swap page topics, reuse the same "
                "evidence as the main point on more than two slides, or fill a "
                "qualitative page with dummy chart/KPI values. Before creating "
                "deck.patch.json, preserve the already-finalized manifest decisions; "
                "the images stage has already handled every planned generate item, so "
                "do not read or edit manifest.json here. Create one patch for all "
                "slides that includes every ready media path and "
                "uses scaffolded source facts plus explicitly user-authorized, visibly "
                "disclosed assumptions. When a page has disclosure_required=true, "
                "visibly include its supplied disclosure_evidence in a subtitle, "
                "source, or note; never promote a missing private fact to positive "
                "copy. For public research, omit an unsupported "
                "optional claim rather than exposing 待补充. Do not recreate deck.json."
            )
        elif report_states["deck_spec.json"] == "failed":
            stage = "deck_spec_repair"
            next_action = (
                "REPAIR_INPUT below contains the fresh report issues and exact "
                "affected slide context. Do not reread the report or deck. Create or "
                "revise a minimal "
                "deck.patch.json containing only the named slide prop/background "
                "paths. The filesystem checkpoint will apply it and then invoke the "
                "single deterministic finalizer; do not run a validator yourself. "
                "Do not reread absent later QA reports, do "
                "not rewrite the full deck, and never copy an "
                "INTERNAL_MODEL_HISTORY_PLACEHOLDER or omitted-tool-argument marker "
                "into a file."
            )
        elif report_states["deck_spec.json"] != "ok":
            stage = "finalize"
            next_action = (
                f"Run exactly one bash tool call: `{finalize_command}`. "
                "The deterministic helper refreshes stale/missing checks in order, "
                "stops at the first actionable failure, compiles HTML only after "
                "hard spec/media checks while retaining advisory truth warnings, and "
                "then runs self-check plus runtime probe. "
                "Do not split it into individual validators or add another command."
            )
        elif report_states["truth_check.json"] != "ok":
            stage = "finalize"
            next_action = (
                f"Run exactly one bash tool call: `{finalize_command}`. "
                "It refreshes the missing or stale advisory truth report, then "
                "continues through the hard media/render/runtime checks. Do not run "
                "a validator separately."
            )
        elif report_states["image_manifest.json"] == "failed":
            stage = "image_qa_repair"
            next_action = (
                "Read only qa/image_manifest.json and repair the named manifest or "
                "deck media paths with one focused edit. Then let the filesystem "
                "checkpoint invoke the single finalizer; do not run another "
                "validator directly, read absent HTML/runtime reports, or restart "
                "authoring."
            )
        else:
            stage = "finalize"
            next_action = (
                f"Run exactly one bash tool call: `{finalize_command}`. "
                "This is the only authorized finalization command: it validates "
                "hard spec and media requirements, records advisory truth warnings, "
                "renders editable HTML, then runs self-check and the 1440x900 runtime "
                "probe. It stops at "
                "the first actionable failure and suppresses large successful "
                "validator payloads. Do not split the chain, rerun discovery, or "
                "scaffold deck.json."
            )

    patch_input = (
        _content_patch_input(outline_path, deck_path, generated_paths)
        if stage == "content_patch" and deck_path is not None
        else None
    )
    scaffold_input = (
        _scaffold_input(outline_path)
        if stage == "scaffold" and outline_path is not None
        else None
    )
    image_input = (
        _image_generation_input(
            manifest_path,
            artifact_root,
            outline_path,
            deck_path,
        )
        if stage == "images" and deck_path is not None
        else None
    )
    repair_input = (
        outline_repair_input
        if stage == "outline_repair"
        else (
            _qa_repair_input(report_dir / "deck_spec.json", deck_path, outline_path)
            if stage == "deck_spec_repair" and deck_path is not None
            else None
        )
    )
    outline_label = str(outline_path.relative_to(Path(workspace_dir))) if outline_path else "missing"
    deck_label = str(deck_path.relative_to(Path(workspace_dir))) if deck_path else "missing"
    patch_label = str(patch_path.relative_to(Path(workspace_dir))) if patch_path.is_file() else "missing"
    html_label = str(html_path.relative_to(Path(workspace_dir))) if html_path else "missing"
    research_input = (
        json.dumps(
            {
                "mode": research_mode,
                "ready": research_ready,
                **({"fallback": True} if research_fallback else {}),
                **(
                    {
                        "fallback_reason": fallback_reason,
                        "fallback_message": fallback_message,
                    }
                    if research_fallback
                    else {}
                ),
                **(
                    {"attempt_summary": research_attempt_summary}
                    if research_attempt_summary is not None
                    else {}
                ),
                "files": [
                    str(
                        path.relative_to(output_root)
                        if path.is_relative_to(output_root)
                        else path.relative_to(Path(workspace_dir))
                    )
                    for path in (research_files if not research_fallback else ())
                ],
                "verified_evidence": (
                    verified_research_evidence if not research_fallback else []
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if research_required
        else None
    )
    return (
        "Internal controlled-presentation checkpoint; filesystem evidence is "
        "authoritative and this instruction overrides any repeated earlier plan.\n"
        f"{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}{stage}\n"
        f"artifacts: outline={outline_label}; deck={deck_label}; "
        f"patch={patch_label}; html={html_label}; "
        f"generated_images={generated_ready}/{generated_expected}; "
        f"generated_statuses={generated_status_ready}/{generated_expected}; "
        f"qa_ok={qa_ready}/{len(_CONTROLLED_PRESENTATION_REPORTS)}; "
        f"qa_warnings={qa_warnings}.\n"
        "Hard rule: never move backward, never recreate an existing deck, and "
        "never pass --force to the scaffold command after downstream artifacts exist.\n"
        + (f"SCAFFOLD_INPUT={scaffold_input}\n" if scaffold_input is not None else "")
        + (f"IMAGE_INPUT={image_input}\n" if image_input is not None else "")
        + (f"PATCH_INPUT={patch_input}\n" if patch_input is not None else "")
        + (f"REPAIR_INPUT={repair_input}\n" if repair_input is not None else "")
        + (f"RESEARCH_INPUT={research_input}\n" if research_input is not None else "")
        + f"NEXT_ACTION={next_action}"
    )


def completion_gate_progress_text(
    gate: CompletionGate,
    workspace_dir: str | None,
) -> str | None:
    """Compatibility adapter for callers that still hold a completion gate."""
    if gate.workflow_checkpoint_kind != WORKFLOW_KIND:
        return None
    research_mode = gate.workflow_options.get(RESEARCH_MODE_OPTION)
    return build_checkpoint_text(
        workspace_dir,
        research_mode if isinstance(research_mode, str) else None,
    )


__all__ = [
    "CONTROLLED_PRESENTATION_CHECKPOINT_MARKER",
    "build_checkpoint_text",
    "completion_gate_progress_text",
]
