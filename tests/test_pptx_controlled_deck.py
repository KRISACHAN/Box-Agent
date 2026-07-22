"""Regression coverage for the controlled HTML deck compiler."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / "box_agent"
    / "skills"
    / "document-skills"
    / "pptx"
)
SCRIPTS_DIR = SKILL_DIR / "scripts"
EXAMPLE = SKILL_DIR / "examples" / "controlled-deck" / "deck.json"
VISUAL_DNA = (
    SKILL_DIR.parents[1]
    / "html-templates"
    / "references"
    / "visual_dna.json"
)
NODE = os.environ.get("BOX_AGENT_NODE") or shutil.which("node")
COMPOSITION_TEMPLATES = {
    "institutional-grid": "ledger",
    "editorial-spread": "spread",
    "poster-asymmetric": "stage",
    "playful-collage": "collage",
    "brutalist-frame": "frame",
    "retro-interface": "window",
    "literary-minimal": "article",
    "product-showcase": "device",
    "cinematic-canvas": "cinema",
    "analytical-exhibit": "exhibit",
    "technical-schematic": "schematic",
}
DEFAULT_COMPOSITION_FAMILIES = {
    "institutional-grid",
    "editorial-spread",
    "poster-asymmetric",
    "playful-collage",
    "brutalist-frame",
    "retro-interface",
    "literary-minimal",
}
COMPOSITION_DIRECTIONS = {
    "structured-systems": [
        "institutional-grid",
        "analytical-exhibit",
        "technical-schematic",
    ],
    "narrative-pages": ["editorial-spread", "literary-minimal"],
    "visual-impact": ["poster-asymmetric", "cinematic-canvas"],
    "interface-modules": ["product-showcase", "retro-interface"],
    "expressive-objects": ["playful-collage", "brutalist-frame"],
}
SPECIALIZED_COMPOSITION_ANCHORS = {
    "product-showcase": "composition-device-screen",
    "cinematic-canvas": "composition-cinema-timecode",
    "analytical-exhibit": "composition-exhibit-board",
    "technical-schematic": "composition-schematic-canvas",
}
STRUCTURAL_VARIANT_ANCHORS = {
    "product-showcase": {
        "device-stage": "composition-device-bezel",
        "browser-story": "composition-device-browserbar",
        "annotated-flow": "composition-device-callouts",
    },
    "analytical-exhibit": {
        "exhibit-grid": "composition-exhibit-key",
        "evidence-rail": "composition-exhibit-scale",
        "decision-board": "composition-exhibit-decisions",
    },
    "technical-schematic": {
        "blueprint-canvas": "composition-schematic-registration",
        "annotated-system": "composition-schematic-bus",
        "spec-sheet": "composition-schematic-spec-rail",
    },
}


def _run(
    script: str,
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if NODE is None:
        pytest.skip("Node.js is required to test the controlled deck compiler")
    return subprocess.run(
        [str(NODE), str(SCRIPTS_DIR / script), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def _write_outline(
    path: Path,
    *,
    page_count: int = 3,
    source_mode: str = "public_authoritative_research",
) -> dict:
    payload = {
        "deck_goal": "用可靠证据解释一个主题",
        "audience": "普通观众",
        "source_mode": source_mode,
        "storyline": "从背景进入关键阶段，再以未来行动收束完整叙事。",
        "slides": [
            {
                "page": index,
                "title": f"主题页 {index}",
                "message": f"第 {index} 页保留自己的核心信息",
                "bullets": [
                    f"第 {index} 页支持点甲",
                    f"第 {index} 页支持点乙",
                ],
                "layout": "cards",
                "visual": "结构化信息卡",
                "evidence": [
                    f"公开资料证据 {chr(64 + index)} | Example | "
                    f"https://example.com/source-{chr(96 + index)}"
                ],
            }
            for index in range(1, page_count + 1)
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92
        if value <= 0.03928
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(left: str, right: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(left), _relative_luminance(right)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_layout_manifest_is_generated_from_registry() -> None:
    result = _run("build_layout_manifest.js", "--check")

    assert result.returncode == 0, result.stderr
    manifest = json.loads((SKILL_DIR / "layouts" / "manifest.json").read_text())
    assert manifest["generated_from"] == "layouts/registry.js + themes/*.json"
    assert manifest["default_theme_id"] == "blue-professional"
    visual_dna_ids = {
        item["template_id"]
        for item in json.loads(VISUAL_DNA.read_text(encoding="utf-8"))["templates"]
    }
    theme_ids = {theme["id"] for theme in manifest["themes"]}
    covered_dna_ids = {
        dna_id
        for theme in manifest["themes"]
        for dna_id in theme["selection"]["visual_dna_ids"]
    }
    assert len(visual_dna_ids) == 32
    assert len(theme_ids) == 34
    assert visual_dna_ids <= theme_ids
    assert covered_dna_ids == visual_dna_ids
    assert {
        direction["id"]: direction["family_ids"]
        for direction in manifest["composition_directions"]
    } == COMPOSITION_DIRECTIONS
    assert {
        family["family"]
        for direction in manifest["composition_directions"]
        for family in direction["families"]
    } == set(COMPOSITION_TEMPLATES)
    assert all(
        family["direction"] == direction["id"]
        and family["selection_signals"]
        and len(family["variants"]) == 3
        for direction in manifest["composition_directions"]
        for family in direction["families"]
    )
    assert all(
        set(theme["style"]) == {
            "canvas",
            "surface",
            "shadow",
            "heading",
            "label",
            "accent",
            "alternation",
        }
        for theme in manifest["themes"]
    )
    composition_families = {
        theme["composition"]["family"] for theme in manifest["themes"]
    }
    assert composition_families == DEFAULT_COMPOSITION_FAMILIES
    assert all(
        len(theme["composition"]["variants"]) == 3
        and len(set(theme["composition"]["variants"])) == 3
        for theme in manifest["themes"]
    )
    selectable_families = {
        family["family"]
        for theme in manifest["themes"]
        for family in theme["composition"]["families"]
    }
    assert selectable_families == set(COMPOSITION_TEMPLATES)
    assert all(
        theme["composition"]["family"]
        == theme["composition"]["default_family"]
        and theme["composition"]["direction"]
        == theme["composition"]["default_direction"]
        and theme["composition"]["default_family"]
        in theme["composition"]["allowed_families"]
        and theme["composition"]["default_direction"]
        in theme["composition"]["allowed_directions"]
        and {
            family
            for direction in theme["composition"]["directions"]
            for family in direction["families"]
        }
        == set(theme["composition"]["allowed_families"])
        and all(len(family["variants"]) == 3 for family in theme["composition"]["families"])
        for theme in manifest["themes"]
    )
    block_frame = next(
        theme for theme in manifest["themes"] if theme["id"] == "block-frame"
    )
    assert block_frame["selection"]["visual_dna_ids"] == ["block-frame"]
    assert block_frame["shape"]["radius_large"] == 0
    mono_blue = next(
        theme
        for theme in manifest["themes"]
        if theme["id"] == "block-frame-mono-blue"
    )
    assert mono_blue["selection"]["visual_dna_ids"] == ["block-frame"]
    assert mono_blue["palette"]["primary"] == "#1E2BFA"
    consulting_navy = next(
        theme for theme in manifest["themes"] if theme["id"] == "consulting-navy"
    )
    assert consulting_navy["selection"]["scheme"] == "cool-light"
    assert consulting_navy["selection"]["formality"] == "high"
    assert consulting_navy["palette"]["background"] == "#F4F7FA"
    assert consulting_navy["palette"]["primary"] == "#173B63"
    assert consulting_navy["composition"]["family"] == "institutional-grid"
    assert len(manifest["layouts"]) == 18
    assert {layout["id"] for layout in manifest["layouts"]} >= {
        "cover-hero-v1",
        "cover-editorial-v1",
        "comparison-two-column-v1",
        "text-columns-v1",
        "architecture-layered-v1",
        "system-integration-v1",
        "dashboard-overview-v1",
        "chart-bar-v1",
        "chart-data-v1",
        "table-data-v1",
        "timeline-horizontal-v1",
        "project-case-study-v1",
        "closing-next-steps-v1",
    }
    assert all(layout["editor"]["defaultProps"] for layout in manifest["layouts"])
    cover = next(layout for layout in manifest["layouts"] if layout["id"] == "cover-hero-v1")
    assert cover["editor"]["defaultProps"]["eyebrow"] == "年度作品集"
    assert cover["mediaSlots"]["decision"]["mode"] == "auto"
    assert cover["mediaSlots"]["slots"][0] == {
        "id": "hero",
        "propPath": "hero",
        "role": "primary-visual",
        "required": False,
        "strategies": ["generate", "use_existing", "skip"],
        "preferredRatio": "4:3",
        "placementControlledBy": "media_side",
    }
    assert all(
        layout["mediaSlots"]["background"]["supported"]
        and layout["mediaSlots"]["background"]["requiresLayoutContract"]
        and layout["mediaSlots"]["background"]["textRegionNames"]
        for layout in manifest["layouts"]
    )
    project = next(
        layout for layout in manifest["layouts"] if layout["id"] == "project-case-study-v1"
    )
    assert project["fields"]["image"]["required"] is False
    assert project["fields"]["metrics"]["minItems"] == 2
    assert project["fields"]["metrics"]["maxItems"] == 3
    assert project["fields"]["composition"]["values"] == ["split", "poster"]
    assert project["mediaSlots"]["slots"][0]["strategies"] == [
        "generate",
        "use_existing",
        "skip",
    ]
    architecture = next(
        layout for layout in manifest["layouts"] if layout["id"] == "architecture-layered-v1"
    )
    assert architecture["fields"]["layers"]["maxItems"] == 6
    table = next(
        layout for layout in manifest["layouts"] if layout["id"] == "table-data-v1"
    )
    assert table["fields"]["columns"]["maxItems"] == 6
    assert table["fields"]["rows"]["maxItems"] == 12
    assert table["fields"]["rows"]["itemShape"]["maxItems"] == 6
    assert "gantt" in table["variants"]
    assert "gantt" in table["fields"]["variant"]["values"]


def test_skill_avoids_public_research_permission_and_micro_todo_loops() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "do not call\n`plan_write` or `todo_write`" in skill
    assert "already authorizes the normal use\n   of public, authoritative sources" in skill
    assert "Do not ask the user\n   for a second \"permission to use public sources\"" in skill
    assert "must not replace it with a separate four-query cap" in skill
    assert "Inspect the full\n   useful result returned by each search" in skill


def test_every_visual_dna_theme_has_complete_contrast_safe_runtime_tokens() -> None:
    manifest = json.loads((SKILL_DIR / "layouts" / "manifest.json").read_text())
    required_palette = {
        "background",
        "surface",
        "surface_strong",
        "primary",
        "primary_soft",
        "text",
        "muted",
        "border",
        "inverse",
        "chart",
    }
    for theme in manifest["themes"]:
        palette = theme["palette"]
        assert required_palette <= set(palette), theme["id"]
        assert len(palette["chart"]) == 4, theme["id"]
        assert all(
            isinstance(color, str)
            and len(color) == 7
            and color.startswith("#")
            for color in [
                palette["background"],
                palette["surface"],
                palette["surface_strong"],
                palette["primary"],
                palette["primary_soft"],
                palette["text"],
                palette["muted"],
                palette["border"],
                palette["inverse"],
                *palette["chart"],
            ]
        ), theme["id"]
        primary_text = palette.get("primary_text", palette["primary"])
        assert _contrast_ratio(palette["text"], palette["background"]) >= 4.5, theme["id"]
        assert _contrast_ratio(palette["muted"], palette["background"]) >= 3, theme["id"]
        assert _contrast_ratio(primary_text, palette["background"]) >= 3, theme["id"]
        assert _contrast_ratio(palette["inverse"], palette["primary"]) >= 4.5, theme["id"]


def test_every_registered_theme_renders_all_controlled_layouts(tmp_path: Path) -> None:
    manifest = json.loads((SKILL_DIR / "layouts" / "manifest.json").read_text())
    layout_ids = [layout["id"] for layout in manifest["layouts"]]
    rendered_templates: set[str] = set()
    deck_path = tmp_path / "all-layouts.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        *layout_ids,
        "--title",
        "Theme compatibility gallery",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert len(deck["slides"]) == 18

    for theme in manifest["themes"]:
        theme_id = theme["id"]
        deck["theme_id"] = theme_id
        deck["design"]["family"] = theme["composition"]["family"]
        deck["design"]["variant"] = theme["composition"]["variants"][0]
        deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
        validation = _run("validate_deck_spec.js", str(deck_path))
        assert validation.returncode == 0, f"{theme_id}: {validation.stdout}"
        html_path = tmp_path / f"{theme_id}.html"
        rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
        assert rendered.returncode == 0, f"{theme_id}: {rendered.stderr}"
        html = html_path.read_text(encoding="utf-8")
        rendered_deck = html.split('<section class="deck-layout-picker"', 1)[0]
        assert rendered_deck.count('<section class="slide ') == 18, theme_id
        assert f'data-deck-theme-id="{theme_id}"' in html
        assert (
            f'data-deck-composition="{theme["composition"]["family"]}"' in html
        )
        template = COMPOSITION_TEMPLATES[theme["composition"]["family"]]
        rendered_templates.add(template)
        assert f'data-composition-template="{template}"' in rendered_deck
        assert f'class="composition-root composition-{template}"' in rendered_deck
        assert any(
            f'data-deck-composition-variant="{variant}"' in html
            for variant in theme["composition"]["variants"]
        )
        for axis in (
            "canvas",
            "surface",
            "shadow",
            "heading",
            "label",
            "accent",
            "alternation",
        ):
            assert f'data-deck-{axis}="{theme["style"][axis]}"' in html
    assert rendered_templates == {
        COMPOSITION_TEMPLATES[family] for family in DEFAULT_COMPOSITION_FAMILIES
    }


@pytest.mark.parametrize(
    ("theme_id", "family"),
    [
        ("blue-professional", "product-showcase"),
        ("studio", "cinematic-canvas"),
        ("blue-professional", "analytical-exhibit"),
        ("blue-professional", "technical-schematic"),
    ],
)
def test_new_composition_families_render_every_layout(
    tmp_path: Path,
    theme_id: str,
    family: str,
) -> None:
    manifest = json.loads((SKILL_DIR / "layouts" / "manifest.json").read_text())
    layout_ids = [layout["id"] for layout in manifest["layouts"]]
    deck_path = tmp_path / family / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        *layout_ids,
        "--theme",
        theme_id,
        "--family",
        family,
        "--design-seed",
        f"{family.replace('-', '_')}_seed",
        "--title",
        f"{family} compatibility gallery",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    contract = json.loads(scaffold.stdout)
    expected_direction = next(
        direction
        for direction, families in COMPOSITION_DIRECTIONS.items()
        if family in families
    )
    assert contract["authoring_rules"]["design_policy"]["selected_direction"] == (
        expected_direction
    )
    assert contract["authoring_rules"]["design_policy"]["user_choice_path"] == (
        "selected_theme.composition.directions"
    )
    assert contract["authoring_rules"]["design_policy"]["family_selection_path"] == (
        "selected_theme.composition.families[].selection_signals"
    )
    assert expected_direction in contract["selected_theme"]["composition"][
        "allowed_directions"
    ]
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["design"]["family"] == family

    validation = _run("validate_deck_spec.js", str(deck_path))
    assert validation.returncode == 0, validation.stdout + validation.stderr
    html_path = deck_path.parent / "index.html"
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    html = html_path.read_text(encoding="utf-8")
    rendered_deck = html.split('<section class="deck-layout-picker"', 1)[0]
    rendered_dom = rendered_deck.split('<main id="deck-root">', 1)[1]
    template = COMPOSITION_TEMPLATES[family]
    assert rendered_deck.count('<section class="slide ') == 18
    assert f'data-deck-composition="{family}"' in html
    assert f'data-composition-template="{template}"' in rendered_deck
    assert f'class="composition-root composition-{template}"' in rendered_deck
    assert SPECIALIZED_COMPOSITION_ANCHORS[family] in rendered_dom
    variant = deck["design"]["variant"]
    if family in STRUCTURAL_VARIANT_ANCHORS:
        assert STRUCTURAL_VARIANT_ANCHORS[family][variant] in rendered_dom

    self_check = _run("html_self_check.js", str(html_path))
    assert self_check.returncode == 0, self_check.stdout + self_check.stderr


def test_theme_gallery_renders_real_opt_in_theme_previews(tmp_path: Path) -> None:
    gallery_path = tmp_path / "theme-previews" / "index.html"

    result = _run(
        "render_theme_gallery.js",
        "--out",
        str(gallery_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["theme_count"] == 8
    assert payload["themes"] == [
        "blue-professional",
        "signal",
        "biennale-yellow",
        "studio",
        "daisy-days",
        "block-frame-mono-blue",
        "retro-windows",
        "soft-editorial",
    ]
    gallery = gallery_path.read_text(encoding="utf-8")
    assert "先看主题，再开始做 PPT" in gallery
    assert "回复卡片上的 theme_id" in gallery
    assert gallery.count("?mode=gallery") == 8
    assert gallery.count("打开 3 页完整预览") == 8
    for theme_id in payload["themes"]:
        preview_path = gallery_path.parent / f"{theme_id}.html"
        preview = preview_path.read_text(encoding="utf-8")
        rendered_preview = preview.split('<section class="deck-layout-picker"', 1)[0]
        assert f'data-deck-theme-id="{theme_id}"' in preview
        assert rendered_preview.count('<section class="slide ') == 3
        assert "data-composition-template=" in rendered_preview
        assert 'id="deck-document"' in preview


def test_composition_gallery_renders_every_family_and_variant(
    tmp_path: Path,
) -> None:
    gallery_path = tmp_path / "composition-previews" / "index.html"
    variants = {
        "institutional-grid": ["balanced-grid", "rail-grid", "ledger-grid"],
        "editorial-spread": ["split-spread", "feature-spread", "banded-spread"],
        "poster-asymmetric": ["offset-hero", "stacked-poster", "split-poster"],
        "playful-collage": ["mosaic", "staggered", "capsule"],
        "brutalist-frame": ["block-grid", "offset-frame", "ledger-frame"],
        "retro-interface": ["window-grid", "terminal-stack", "pixel-panels"],
        "literary-minimal": ["margin-note", "quiet-center", "asymmetric-column"],
        "product-showcase": ["device-stage", "browser-story", "annotated-flow"],
        "cinematic-canvas": ["full-bleed", "split-film", "chapter-cut"],
        "analytical-exhibit": ["exhibit-grid", "evidence-rail", "decision-board"],
        "technical-schematic": ["blueprint-canvas", "annotated-system", "spec-sheet"],
    }

    result = _run(
        "render_composition_gallery.js",
        "--out",
        str(gallery_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["family_count"] == 11
    assert payload["variant_count"] == 33
    assert {
        group["id"]: group["families"] for group in payload["groups"]
    } == COMPOSITION_DIRECTIONS
    assert {
        family
        for group in payload["groups"]
        for family in group["families"]
    } == set(variants)
    gallery = gallery_path.read_text(encoding="utf-8")
    assert "看骨架，不看换色" in gallery
    assert "用户只需要理解 5 个方向" in gallery
    assert "内容信号" in gallery
    assert gallery.count("?mode=gallery") == 33

    for family, family_variants in variants.items():
        assert family in gallery
        for variant in family_variants:
            preview_path = gallery_path.parent / f"{family}--{variant}.html"
            preview = preview_path.read_text(encoding="utf-8")
            rendered_preview = preview.split('<section class="deck-layout-picker"', 1)[0]
            rendered_dom = rendered_preview.split('<main id="deck-root">', 1)[1]
            assert f'data-deck-composition="{family}"' in preview
            assert f'data-deck-composition-variant="{variant}"' in preview
            assert rendered_preview.count('<section class="slide ') == 1
            structural_anchors = STRUCTURAL_VARIANT_ANCHORS.get(family, {})
            if structural_anchors:
                assert structural_anchors[variant] in rendered_dom
                assert all(
                    anchor not in rendered_dom
                    for other_variant, anchor in structural_anchors.items()
                    if other_variant != variant
                )

    for family in SPECIALIZED_COMPOSITION_ANCHORS:
        for variant in variants[family]:
            self_check = _run(
                "html_self_check.js",
                str(gallery_path.parent / f"{family}--{variant}.html"),
            )
            assert self_check.returncode == 0, self_check.stdout + self_check.stderr


def test_restrained_information_families_do_not_reuse_pill_label_chrome() -> None:
    composition_css = (SKILL_DIR / "runtime" / "composition.css").read_text(
        encoding="utf-8"
    )
    label_rules = composition_css.split(
        "/* Restrained information families", 1
    )[1].split("/* --------------------------------------------------------------------------", 1)[0]

    for family in (
        "institutional-grid",
        "literary-minimal",
        "product-showcase",
        "analytical-exhibit",
        "technical-schematic",
    ):
        assert f'body[data-deck-composition="{family}"]' in label_rules
    assert "border-radius: 0;" in label_rules
    assert "background: transparent;" in label_rules
    assert "transform: none;" in label_rules


def test_soft_editorial_replaces_repeated_rules_with_pastel_panels() -> None:
    composition_css = (SKILL_DIR / "runtime" / "composition.css").read_text(
        encoding="utf-8"
    )
    soft_rules = composition_css.split(
        "/* Soft Editorial uses quiet pastel surfaces", 1
    )[1].split("/* The layout picker renders miniature slides", 1)[0]

    theme_selector = (
        'body[data-deck-theme-id="soft-editorial"]'
        '[data-deck-composition="editorial-spread"]'
    )
    assert f"{theme_selector} .slide-header" in soft_rules
    assert f"{theme_selector} .content-card" in soft_rules
    assert f"{theme_selector} .comparison-column" in soft_rules
    assert f"{theme_selector} .timeline-step" in soft_rules
    assert "border-bottom: 0;" in soft_rules
    assert "border-top: 0;" in soft_rules
    assert "border-radius: var(--deck-radius-large);" in soft_rules
    assert "background: var(--deck-primary-soft);" in soft_rules


def test_theme_gallery_is_opt_in_and_precedes_deck_checkpoint() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    theme_factory = (
        SKILL_DIR.parents[1] / "theme-factory" / "SKILL.md"
    ).read_text(encoding="utf-8")
    editor = (SKILL_DIR / "runtime" / "deck-editor.js").read_text(encoding="utf-8")

    assert "Theme preview intent (before deck authoring)" in skill
    assert "theme discovery" in skill
    assert "must not slow the default path" in skill
    assert "Before writing `outline.json`, scaffolding" in skill
    assert "scripts/render_theme_gallery.js" in skill
    assert "Composition comparison intent" in skill
    assert "scripts/render_composition_gallery.js" in skill
    assert "layout.render(modelSlide, index, documentModel.design)" in editor
    assert "PPT ownership boundary (mandatory)" in theme_factory
    assert 'get_skill(skill_name="pptx")' in theme_factory
    assert "Do not list the ten themes below" in theme_factory


def test_design_seed_is_reproducible_and_selects_distinct_variants(
    tmp_path: Path,
) -> None:
    designs = []
    for index, seed in enumerate(("seed_alpha", "seed_bravo", "seed_foxtrot"), 1):
        deck_path = tmp_path / f"variant-{index}" / "deck.json"
        scaffold = _run(
            "inspect_deck_contract.js",
            "cover-hero-v1",
            "cards-grid-v1",
            "--theme",
            "blue-professional",
            "--design-seed",
            seed,
            "--out",
            str(deck_path),
        )
        assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
        design = json.loads(deck_path.read_text(encoding="utf-8"))["design"]
        assert design["seed"] == seed
        assert design["family"] == "institutional-grid"
        designs.append(design)

        html_path = deck_path.parent / "index.html"
        first = _run(
            "render_deck_html.js", str(deck_path), "--out", str(html_path)
        )
        assert first.returncode == 0, first.stdout + first.stderr
        first_bytes = html_path.read_bytes()
        second = _run(
            "render_deck_html.js", str(deck_path), "--out", str(html_path)
        )
        assert second.returncode == 0, second.stdout + second.stderr
        assert html_path.read_bytes() == first_bytes

    assert {design["variant"] for design in designs} == {
        "balanced-grid",
        "rail-grid",
        "ledger-grid",
    }


def test_friendly_onboarding_auto_corrects_fallback_theme_and_avoids_schematic(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=3,
        source_mode="user_provided",
    )
    outline.update(
        {
            "deck_goal": "为新员工提供一场清爽亲和、会议室可讲的入职培训。",
            "audience": "刚入职的新员工",
            "storyline": "从欢迎开始，用模块卡片和时间线讲清公司、文化与制度。",
        }
    )
    outline["slides"][0].update(
        {
            "title": "欢迎加入：一起把 AI 办公变得更好用",
            "layout": "浅色欢迎封面",
            "visual": "柔和品牌色小色块与欢迎插画",
        }
    )
    outline["slides"][1].update(
        {
            "title": "今天我们会讲什么",
            "layout": "模块卡片",
            "visual": "五个浅色模块卡片，每个模块配一个线性图标",
        }
    )
    outline["slides"][2].update(
        {
            "title": "入职节奏",
            "layout": "横向时间线",
            "visual": "从账号开通到团队融入的横向流程",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "auto" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "cards-grid-v1",
        "timeline-horizontal-v1",
        "--theme",
        "blue-professional",
        "--outline",
        str(outline_path),
        "--title",
        "新员工入职培训",
        "--fact",
        "清爽亲和，浅色背景为主，多用图标和小色块",
        "--fact",
        "不要深色高冷、不要复古手绘、不要拼贴",
        "--fact",
        "浅底加一两个柔和的品牌色点缀",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    report = json.loads(
        (deck_path.parent / "qa" / "deck_contract.json").read_text()
    )
    assert deck["theme_id"] == "soft-editorial"
    assert deck["design"]["family"] == "editorial-spread"
    assert report["theme_selection"]["source"] == "auto_corrected_default"
    assert report["theme_selection"]["confidence"] == "high"
    assert report["design_selection"]["family"] == "editorial-spread"
    assert report["design_selection"]["scores"].get("technical-schematic", 0) == 0


def test_theme_inference_does_not_treat_negated_playful_style_as_positive(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=3,
        source_mode="user_provided",
    )
    outline.update(
        {
            "deck_goal": "为连锁零售集团生成稳健可落地的智能客服评标方案。",
            "audience": "客户采购负责人、IT 负责人和业务负责人",
            "storyline": "从客户需求、解决方案到业务价值与实施计划。",
        }
    )
    outline["slides"][0].update(
        {
            "title": "某连锁零售集团智能客服升级",
            "layout": "浅底咨询风封面",
            "visual": "深蓝、钢灰和浅灰的规整封面",
        }
    )
    outline["slides"][1].update(
        {
            "title": "需求与方案",
            "layout": "规整的咨询公司式卡片",
            "visual": "极简装饰与高信息密度",
        }
    )
    outline["slides"][2].update(
        {
            "title": "实施计划",
            "layout": "规整时间线",
            "visual": "可落地的阶段式计划",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "selection" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "cards-grid-v1",
        "timeline-horizontal-v1",
        "--theme",
        "auto",
        "--outline",
        str(outline_path),
        "--title",
        "智能客服评标方案",
        "--fact",
        "整体风格要稳健、专业、可信、可落地",
        "--fact",
        "浅底，深蓝 / 钢灰 / 浅灰冷色调，版式规整，装饰极简",
        "--fact",
        "不要做成投资人路演风、文艺杂志风、活泼亲和风或花哨拼贴风",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    report = json.loads(
        (deck_path.parent / "qa" / "deck_contract.json").read_text()
    )
    assert deck["theme_id"] == "consulting-navy"
    assert report["theme_selection"]["theme_id"] == "consulting-navy"
    signals = {
        item["signal"] for item in report["theme_selection"]["matched_signals"]
    }
    assert "cool consulting review signature" in signals
    assert "friendly mood" not in signals
    assert "lively supporting mood" not in signals
    assert "friendly lively signature" not in signals


def test_lock_theme_preserves_explicit_user_choice_for_onboarding(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=2,
        source_mode="user_provided",
    )
    outline["deck_goal"] = "清爽亲和的新员工入职培训"
    outline["audience"] = "刚入职的新员工"
    outline["storyline"] = "从欢迎进入内部培训模块。"
    outline["slides"][0]["layout"] = "浅色欢迎封面"
    outline["slides"][0]["visual"] = "柔和品牌色封面"
    outline["slides"][1]["layout"] = "模块卡片"
    outline["slides"][1]["visual"] = "浅色模块卡片"
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "locked" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "cards-grid-v1",
        "--theme",
        "blue-professional",
        "--lock-theme",
        "--outline",
        str(outline_path),
        "--title",
        "新员工入职培训",
        "--fact",
        "清爽亲和，浅色背景为主",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    report = json.loads(
        (deck_path.parent / "qa" / "deck_contract.json").read_text()
    )
    assert deck["theme_id"] == "blue-professional"
    assert deck["design"]["family"] == "institutional-grid"
    assert report["theme_selection"]["source"] == "explicit_locked"


def test_theme_family_allowlist_preserves_compatible_choice_and_rejects_mismatch(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "compatible" / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "chart-data-v1",
        "--theme",
        "blue-professional",
        "--family",
        "analytical-exhibit",
        "--design-seed",
        "compatible_seed",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["design"]["family"] == "analytical-exhibit"

    validation = _run("validate_deck_spec.js", str(deck_path))
    assert validation.returncode == 0, validation.stdout + validation.stderr
    html_path = deck_path.parent / "index.html"
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    html = html_path.read_text(encoding="utf-8")
    assert 'data-deck-composition="analytical-exhibit"' in html
    assert 'data-composition-template="exhibit"' in html

    rejected = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--theme",
        "retro-windows",
        "--family",
        "technical-schematic",
        "--design-seed",
        "mismatch_seed",
    )
    assert rejected.returncode == 1
    assert "not allowed for theme retro-windows" in rejected.stderr
    assert "retro-interface, product-showcase, cinematic-canvas" in rejected.stderr


def test_scaffold_infers_product_family_and_cover_image_from_outline(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "product-outline.json"
    outline = _write_outline(outline_path)
    outline["deck_goal"] = "展示桌面客户端的产品能力与用户流程"
    outline["storyline"] = "从产品主界面进入功能工作流，最后给出下一步。"
    outline["slides"][0].update(
        {
            "title": "把本地工作流放进一个客户端",
            "message": "首页需要让观众一眼理解产品形态。",
            "layout": "cover",
            "visual": "客户端主界面 hero，包含文档、表格、PPT 与本地图标",
        }
    )
    outline["slides"][1].update(
        {
            "message": "用功能卡片解释产品流程。",
            "visual": "产品功能卡片与用户流程",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "product" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "cards-grid-v1",
        "closing-next-steps-v1",
        "--theme",
        "blue-professional",
        "--title",
        "Box Agent 客户端",
        "--outline",
        str(outline_path),
        "--image-mode",
        "auto",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    report = json.loads(
        (deck_path.parent / "qa" / "deck_contract.json").read_text()
    )
    manifest = json.loads(
        (deck_path.parent / "assets" / "generated" / "manifest.json").read_text()
    )
    assert deck["design"]["family"] == "product-showcase"
    assert report["design_selection"]["source"] == "content_inference"
    assert report["design_selection"]["family"] == "product-showcase"
    assert report["design_selection"]["matched_signals"]
    cover = manifest["image_plan"][0]
    assert cover["decision"] == "generate"
    assert cover["required"] is True
    assert "product or interface cover visual" in cover["decision_reason"]
    assert "conceptual product-interface illustration" in cover["prompt"]
    assert "No embedded text, no logos, no watermark" in cover["prompt"]


def test_scaffold_promotes_person_profile_cover_from_slide_visual(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "profile-outline.json"
    outline = _write_outline(outline_path)
    outline["deck_goal"] = "用权威资料介绍拉明·亚马尔的履历与成长路径。"
    outline["storyline"] = "从基础身份、成长路径到关键纪录和未来看点。"
    outline["slides"][0].update(
        {
            "title": "拉明·亚马尔：打破年龄边界的新星",
            "message": "先建立主角识别度与整套演示的叙事基调。",
            "layout": "cover",
            "visual": "人物海报式封面，强调年轻、速度与聚光灯感",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "profile" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "cards-grid-v1",
        "closing-next-steps-v1",
        "--outline",
        str(outline_path),
        "--image-mode",
        "auto",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    manifest = json.loads(
        (deck_path.parent / "assets" / "generated" / "manifest.json").read_text()
    )
    cover = manifest["image_plan"][0]
    assert cover["slot"] == "hero"
    assert cover["decision"] == "generate"
    assert cover["required"] is True
    assert "visual story" in cover["decision_reason"]
    assert "人物海报式封面" in cover["prompt"]


def test_scaffold_infers_technical_family_from_code_and_system_outline(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "technical-outline.json"
    outline = _write_outline(outline_path)
    outline["deck_goal"] = "解释 Agent 运行时的系统架构与协作方式"
    outline["storyline"] = "从代码执行入口进入协作节点和运行时数据流。"
    outline["slides"][0].update(
        {
            "title": "一个可观察的 Agent 运行时",
            "message": "封面先建立代码与系统连接关系。",
            "layout": "cover",
            "visual": "代码窗口连接多个协作节点的技术架构图",
        }
    )
    outline["slides"][1].update(
        {
            "message": "沿着运行时数据流解释模块协作。",
            "visual": "系统架构、模块接口与数据流节点",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "technical" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "timeline-horizontal-v1",
        "closing-next-steps-v1",
        "--theme",
        "blue-professional",
        "--outline",
        str(outline_path),
        "--image-mode",
        "auto",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    report = json.loads(
        (deck_path.parent / "qa" / "deck_contract.json").read_text()
    )
    manifest = json.loads(
        (deck_path.parent / "assets" / "generated" / "manifest.json").read_text()
    )
    assert deck["design"]["family"] == "technical-schematic"
    assert report["design_selection"]["source"] == "content_inference"
    assert manifest["image_plan"][0]["decision"] == "generate"
    assert "code or technical-system cover visual" in (
        manifest["image_plan"][0]["decision_reason"]
    )


def test_explicit_family_overrides_outline_inference(tmp_path: Path) -> None:
    outline_path = tmp_path / "product-outline.json"
    outline = _write_outline(outline_path)
    outline["deck_goal"] = "展示产品主界面与功能流程"
    outline["slides"][0]["visual"] = "客户端主界面 UI 截图"
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "explicit" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "cards-grid-v1",
        "closing-next-steps-v1",
        "--theme",
        "blue-professional",
        "--family",
        "analytical-exhibit",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    report = json.loads(
        (deck_path.parent / "qa" / "deck_contract.json").read_text()
    )
    assert deck["design"]["family"] == "analytical-exhibit"
    assert report["design_selection"]["source"] == "explicit_family"


def test_single_theme_record_can_define_composition_policy_without_legacy_mapping() -> None:
    if NODE is None:
        pytest.skip("Node.js is required to test composition policy")
    core = SCRIPTS_DIR / "composition_core.js"
    probe = """
const composition = require(process.argv[1]);
const theme = {
  id: "single-file-theme",
  composition: {
    default_family: "literary-minimal",
    allowed_families: ["literary-minimal", "cinematic-canvas"],
  },
};
const manifest = composition.compositionManifestRecord(theme);
const design = composition.createDeckDesign(theme, "single_file_seed", "cinematic-canvas");
process.stdout.write(JSON.stringify({ manifest, design }));
"""
    result = subprocess.run(
        [str(NODE), "-e", probe, str(core)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["manifest"]["default_family"] == "literary-minimal"
    assert payload["manifest"]["allowed_families"] == [
        "literary-minimal",
        "cinematic-canvas",
    ]
    assert payload["manifest"]["default_direction"] == "narrative-pages"
    assert payload["manifest"]["allowed_directions"] == [
        "narrative-pages",
        "visual-impact",
    ]
    assert payload["design"]["family"] == "cinematic-canvas"
    assert payload["design"]["variant"] in {
        "full-bleed",
        "split-film",
        "chapter-cut",
    }


def test_editor_defaults_and_every_layout_migration_validate() -> None:
    if NODE is None:
        pytest.skip("Node.js is required to test the controlled deck compiler")
    registry = SKILL_DIR / "layouts" / "registry.js"
    core = SCRIPTS_DIR / "deck_spec_core.js"
    probe = """
const registry = require(process.argv[1]);
const core = require(process.argv[2]);
const slides = registry.layouts.map((layout, index) => ({
  id: `slide-${index + 1}`,
  layout_id: layout.id,
  props: registry.createEditorProps(layout.id),
}));
const deck = {
  schema_version: 1,
  title: "Editor contracts",
  theme_id: "blue-professional",
  slides,
};
const defaults = core.validateAndNormalizeDeck(deck);
if (!defaults.ok) throw new Error(defaults.issues.join("\\n"));
const pathParts = value => String(value).split(".").filter(Boolean);
const getAtPath = (target, value) => pathParts(value).reduce(
  (cursor, part) => cursor && cursor[part],
  target
);
const contractAtPath = (layout, value) => {
  const parts = pathParts(value);
  let fields = layout.fields;
  let contract = null;
  for (let index = 0; index < parts.length; index += 1) {
    contract = fields && fields[parts[index]];
    if (!contract) return null;
    if (index < parts.length - 1) fields = contract.shape;
  }
  return contract;
};
let enumControls = 0;
let collectionControls = 0;
for (const layout of registry.layouts) {
  const controls = layout.editor.controls || {};
  for (const [pathValue, config] of Object.entries(controls.enums || {})) {
    const contract = contractAtPath(layout, pathValue);
    if (!contract || contract.type !== "enum") throw new Error(`${layout.id}.${pathValue} is not enum`);
    const declared = [...contract.values].sort();
    const labeled = Object.keys(config.options || {}).sort();
    if (JSON.stringify(declared) !== JSON.stringify(labeled)) {
      throw new Error(`${layout.id}.${pathValue} enum labels do not match contract`);
    }
    enumControls += 1;
  }
  for (const [pathValue, config] of Object.entries(controls.collections || {})) {
    const contract = contractAtPath(layout, pathValue);
    const props = JSON.parse(JSON.stringify(layout.editor.defaultProps));
    const items = getAtPath(props, pathValue);
    if (!contract || contract.type !== "array" || !Array.isArray(items)) {
      throw new Error(`${layout.id}.${pathValue} is not an editable array`);
    }
    if (items.length >= contract.maxItems) throw new Error(`${layout.id}.${pathValue} has no add capacity`);
    items.push(JSON.parse(JSON.stringify(config.itemDefault)));
    const candidate = core.validateAndNormalizeDeck({
      ...deck,
      slides: [{ id: "control-probe", layout_id: layout.id, props }],
    });
    if (!candidate.ok) throw new Error(candidate.issues.join("\\n"));
    collectionControls += 1;
  }
}
let migrations = 0;
for (const source of slides) {
  for (const target of slides) {
    const candidate = {
      ...deck,
      slides: [{
        id: "probe",
        layout_id: target.layout_id,
        props: registry.createEditorProps(target.layout_id, source),
        layout_drafts: { [source.layout_id]: source.props },
      }],
    };
    const result = core.validateAndNormalizeDeck(candidate);
    if (!result.ok) {
      throw new Error(`${source.layout_id} -> ${target.layout_id}\\n${result.issues.join("\\n")}`);
    }
    migrations += 1;
  }
}
console.log(JSON.stringify({ layouts: slides.length, migrations, enumControls, collectionControls }));
"""

    result = subprocess.run(
        [str(NODE), "-e", probe, str(registry), str(core)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "layouts": 18,
        "migrations": 324,
        "enumControls": 24,
        "collectionControls": 16,
    }


def test_layout_query_filters_role_density_and_media_capacity() -> None:
    result = _run(
        "query_layouts.js",
        "--role",
        "comparison",
        "--density",
        "medium-high",
        "--media-count",
        "0",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [layout["id"] for layout in payload["layouts"]] == [
        "comparison-two-column-v1"
    ]
    assert payload["layouts"][0]["score"] == 135


def test_compact_theme_and_layout_list_aliases_are_supported() -> None:
    themes = _run("inspect_deck_contract.js", "--list-themes")
    layouts = _run("query_layouts.js", "--list")

    assert themes.returncode == 0, themes.stderr
    assert layouts.returncode == 0, layouts.stderr
    theme_payload = json.loads(themes.stdout)
    layout_payload = json.loads(layouts.stdout)
    theme_ids = [item["id"] for item in theme_payload["themes"]]
    assert theme_payload["composition_directions"] == list(COMPOSITION_DIRECTIONS)
    assert len(theme_ids) == 34
    assert theme_ids == sorted(theme_ids)
    assert {"signal", "studio", "vellum", "8-bit-orbit"} <= set(theme_ids)
    assert layout_payload["count"] == 18
    assert {item["id"] for item in layout_payload["layouts"]} >= {
        "architecture-layered-v1",
        "system-integration-v1",
        "dashboard-overview-v1",
        "project-case-study-v1",
        "image-hero-split-v1",
        "chart-bar-v1",
        "chart-data-v1",
        "table-data-v1",
    }
    assert len(themes.stdout) + len(layouts.stdout) < 23_700


def test_scaffold_normalizes_known_semantic_theme_alias(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--theme",
        "carnival",
        "--title",
        "巴西足球历史",
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["selected_theme"]["id"] == "bold-poster"
    assert payload["theme_id_normalization"] == {
        "from": "carnival",
        "to": "bold-poster",
    }
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["theme_id_normalization"] == payload["theme_id_normalization"]
    assert json.loads(deck_path.read_text())["theme_id"] == "bold-poster"


def test_deck_contract_scaffolds_ordered_repeated_layouts_once(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "image-hero-split-v1",
        "image-hero-split-v1",
        "--theme",
        "block-frame",
        "--title",
        "NOON Studio",
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["default_theme_id"] == "blue-professional"
    assert payload["selected_theme"]["id"] == "block-frame"
    assert [layout["id"] for layout in payload["layouts"]] == [
        "cover-hero-v1",
        "image-hero-split-v1",
    ]
    assert payload["layouts"][0]["fields"]["hero"]["type"] == "media"
    assert payload["layouts"][1]["fields"]["image"]["required"] is True
    assert payload["deck_skeleton"]["theme_id"] == "block-frame"
    assert payload["deck_skeleton"]["design"]["version"] == 1
    assert len(payload["deck_skeleton"]["design"]["seed"]) == 16
    assert payload["deck_skeleton"]["design"]["family"] == "brutalist-frame"
    assert payload["deck_skeleton"]["design"]["variant"] in {
        "block-grid",
        "offset-frame",
        "ledger-frame",
    }
    assert payload["deck_skeleton"]["truth_contract"] == {
        "mode": "source_bound",
        "source_facts": [],
        "assumptions": [],
    }
    assert payload["deck_skeleton"]["slides"][0]["props"]["hero"] is None
    assert [slide["layout_id"] for slide in payload["deck_skeleton"]["slides"]] == [
        "cover-hero-v1",
        "image-hero-split-v1",
        "image-hero-split-v1",
    ]
    assert json.loads(deck_path.read_text()) == payload["deck_skeleton"]
    assert payload["deck_file"] == str(deck_path.resolve())
    image_manifest = deck_path.parent / "assets" / "generated" / "manifest.json"
    assert payload["image_manifest"] == str(image_manifest.resolve())
    image_payload = json.loads(image_manifest.read_text())
    assert image_payload["mode"] == "auto"
    assert image_payload["deck"]["design"] == payload["deck_skeleton"]["design"]
    assert len(image_payload["image_plan"]) == 3
    assert image_payload["image_plan"][0]["slot"] == "hero"
    assert image_payload["image_plan"][0]["decision"] == "skip"
    assert image_payload["image_plan"][1]["slot"] == "image"
    assert image_payload["image_plan"][1]["decision"] == "generate"
    assert image_payload["image_plan"][1]["status"] == "pending"
    contract_report = deck_path.parent / "qa" / "deck_contract.json"
    assert payload["contract_report"] == str(contract_report.resolve())
    contract_payload = json.loads(contract_report.read_text())
    assert contract_payload["ok"] is True
    assert contract_payload["slide_count"] == 3
    assert contract_payload["image_mode"] == "auto"
    assert contract_payload["design"] == payload["deck_skeleton"]["design"]
    assert contract_payload["layout_plan"] == [
        "cover-hero-v1",
        "image-hero-split-v1",
        "image-hero-split-v1",
    ]
    assert len(contract_payload["contract_hash"]) == 64
    assert payload["authoring_rules"]["write_policy"]["initial_full_deck_writes"] == 0
    assert payload["authoring_rules"]["write_policy"]["initial_scaffold_writes"] == 1
    assert payload["authoring_rules"]["write_policy"]["batch_patch_command"].startswith(
        "Write deck.patch.json once, then run ${BOX_AGENT_NODE:-node} "
    )

    repeated = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--out",
        str(deck_path),
    )
    assert repeated.returncode == 1
    assert "Refusing to overwrite existing deck skeleton" in repeated.stderr

    original_deck = deck_path.read_text(encoding="utf-8")
    (deck_path.parent / "deck.patch.json").write_text("{}", encoding="utf-8")
    forced_reset = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--out",
        str(deck_path),
        "--force",
    )
    assert forced_reset.returncode == 1
    assert "Refusing --force reset because downstream deck artifacts" in forced_reset.stderr
    assert deck_path.read_text(encoding="utf-8") == original_deck


def test_scaffold_binds_outline_pages_and_imports_public_research_evidence(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(outline_path)
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "cards-grid-v1",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert [slide["source_outline_page"] for slide in deck["slides"]] == [1, 2, 3]
    assert deck["truth_contract"]["research_facts"] == [
        slide["evidence"][0] for slide in outline["slides"]
    ]
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["outline_binding"]["outline_file"] == str(outline_path.resolve())
    assert report["outline_binding"]["source_mode"] == (
        "public_authoritative_research"
    )
    assert report["outline_binding"]["page_count"] == 3
    assert report["outline_binding"]["evidence_import_count"] == 3
    assert len(report["outline_binding"]["outline_hash"]) == 64
    payload = json.loads(result.stdout)
    assert payload["authoring_rules"]["outline_policy"]["pages"][1]["title"] == (
        "主题页 2"
    )


def test_scaffold_rejects_outline_count_and_normalizes_qualitative_quantitative_layout(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    _write_outline(outline_path)

    count_mismatch = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(tmp_path / "count-mismatch.json"),
    )
    assert count_mismatch.returncode == 1
    assert "contains 3 page(s)" in count_mismatch.stderr
    assert "ordered layout plan contains 2" in count_mismatch.stderr

    qualitative_chart = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "kpi-grid-v1",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(tmp_path / "qualitative-chart.json"),
    )
    assert qualitative_chart.returncode == 0, qualitative_chart.stderr
    contract = json.loads(qualitative_chart.stdout)
    assert contract["layout_normalizations"] == [
        {
            "slide": 2,
            "from": "kpi-grid-v1",
            "to": "cards-grid-v1",
            "reason": (
                "qualitative outline pages use a safe editable cards layout "
                "instead of invented chart or KPI values"
            ),
        }
    ]
    deck = json.loads((tmp_path / "qualitative-chart.json").read_text())
    assert [slide["layout_id"] for slide in deck["slides"]] == [
        "cards-grid-v1",
        "cards-grid-v1",
        "cards-grid-v1",
    ]


def test_scaffold_recovers_architecture_integration_and_qualitative_dashboard(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline_path.write_text(
        json.dumps(
            {
                "deck_goal": "说明智能客服解决方案如何落地",
                "audience": "采购、业务与 IT 评审人",
                "source_mode": "user_provided",
                "storyline": "从技术架构进入系统集成，再以管理闭环收束。",
                "slides": [
                    {
                        "page": 1,
                        "title": "真实技术分层架构",
                        "message": "按职责边界组织各层能力。",
                        "bullets": ["触点、AI 服务、业务集成与运营治理分层"],
                        "layout": "architecture-layered-v1",
                        "visual": "分层架构图，包含触点、AI 服务、业务系统与安全运维模块",
                        "evidence": [],
                    },
                    {
                        "page": 2,
                        "title": "系统集成与数据流设计",
                        "message": "中心平台与现有系统双向连接。",
                        "bullets": ["连接订单、会员、CRM、工单和统一认证"],
                        "layout": "system-integration-v1",
                        "visual": "系统集成图，平台居中并标注与外围系统的数据流",
                        "evidence": [],
                    },
                    {
                        "page": 3,
                        "title": "数据看板与管理闭环",
                        "message": "先定义管理指标域，接入后再呈现真实值。",
                        "bullets": ["关注效率、体验、分流、知识与稳定性"],
                        "layout": "dashboard-overview-v1",
                        "visual": "管理驾驶舱示意，不展示未经提供的数值",
                        "evidence": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "kpi-grid-v1",
        "kpi-grid-v1",
        "kpi-grid-v1",
        "--theme",
        "auto",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    contract = json.loads(result.stdout)
    assert [item["to"] for item in contract["layout_normalizations"]] == [
        "architecture-layered-v1",
        "system-integration-v1",
        "dashboard-overview-v1",
    ]
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert [slide["layout_id"] for slide in deck["slides"]] == [
        "architecture-layered-v1",
        "system-integration-v1",
        "dashboard-overview-v1",
    ]

    html_path = tmp_path / "index.html"
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    html = html_path.read_text(encoding="utf-8")
    assert "layout-architecture" in html
    assert 'class="architecture-layers" data-layout-region="content"' in html
    assert 'class="architecture-stack" data-layout-region="content"' not in html
    assert 'class="architecture-module"' in html
    assert 'class="architecture-module-text"' in html
    assert "layout-system-integration" in html
    assert "layout-dashboard-overview" in html

    report_path = tmp_path / "html-self-check.json"
    self_check = _run(
        "html_self_check.js",
        str(html_path),
        "--dom-to-pptx",
        "--allow-local-images",
        "--report",
        str(report_path),
    )
    assert self_check.returncode == 0, self_check.stdout + self_check.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert not any(
        "short background text uses vertical padding" in warning
        for warning in report["warnings"]
    )


def test_quantitative_dashboard_keeps_kpi_layout(tmp_path: Path) -> None:
    outline_path = tmp_path / "outline.json"
    outline_path.write_text(
        json.dumps(
            {
                "deck_goal": "复盘客服运营指标",
                "audience": "管理层",
                "source_mode": "user_provided",
                "storyline": "用真实指标说明运营表现。",
                "slides": [
                    {
                        "page": 1,
                        "title": "客服数据看板",
                        "message": "机器人解决率为 68%。",
                        "bullets": ["转人工率为 21%"],
                        "layout": "dashboard-overview-v1",
                        "visual": "数据看板，展示机器人解决率与转人工率",
                        "evidence": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "dashboard-overview-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["layout_id"] == "kpi-grid-v1"


def test_scaffold_accepts_user_provided_quantitative_outline_without_links(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline_path.write_text(
        json.dumps(
            {
                "deck_goal": "复盘客服指标变化",
                "audience": "管理层",
                "source_mode": "user_provided",
                "storyline": "用前后对比说明客服效率变化。",
                "slides": [
                    {
                        "page": 1,
                        "title": "改进结果",
                        "message": "首次响应时间从 18 分钟降到 7 分钟。",
                        "bullets": [
                            "一次解决率从 68% 提升到 81%",
                            "满意度从 4.2/5 提升到 4.6/5",
                        ],
                        "layout": "可编辑图表页",
                        "visual": "可编辑前后对比柱状图",
                        "evidence": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["layout_id"] == "chart-data-v1"
    outline_check = _run("validate_outline.js", str(outline_path), "--min-slides", "1")
    assert outline_check.returncode == 0, outline_check.stdout + outline_check.stderr
    assert json.loads(outline_check.stdout)["warnings"] == []


def test_scaffold_persists_visual_intent_and_normalizes_strong_layout_mismatches(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=4,
        source_mode="user_provided",
    )
    outline.update(
        {
            "deck_goal": "把业务规划整理成内部沟通用的汇报",
            "audience": "内部产品、研发与管理团队",
            "storyline": "从四条主线进入能力路径、风险矩阵和月底目标。",
        }
    )
    outline["slides"][0].update(
        {"layout": "cover", "visual": "标题封面 + 四条主线标签"}
    )
    outline["slides"][1].update(
        {"layout": "cards", "visual": "三段式能力路径"}
    )
    outline["slides"][2].update(
        {
            "layout": "matrix",
            "visual": "风险/依赖矩阵：事项、依据、影响、收口动作",
        }
    )
    outline["slides"][3].update(
        {"layout": "closing", "visual": "四象限目标状态卡片 + 下一步观察项"}
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "cards-grid-v1",
        "cards-grid-v1",
        "table-data-v1",
        "--theme",
        "blue-professional",
        "--title",
        "8月业务规划",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert payload["contract_version"] == 2
    assert [slide["layout_id"] for slide in deck["slides"]] == [
        "cover-editorial-v1",
        "cards-grid-v1",
        "table-data-v1",
        "cards-grid-v1",
    ]
    assert [item["slide"] for item in payload["layout_normalizations"]] == [1, 3, 4]
    assert len(deck["slides"][3]["props"]["items"]) == 4
    assert payload["authoring_rules"]["outline_policy"]["pages"][3][
        "expected_visual_item_count"
    ] == 4
    assert deck["slides"][0]["outline_intent"] == {
        key: outline["slides"][0][key]
        for key in ("title", "message", "layout", "visual")
    }
    assert deck["design"]["family"] == "institutional-grid"


def test_scaffold_and_patch_support_six_column_nine_row_gantt(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    outline["slides"][0].update(
        {
            "title": "实施计划与里程碑甘特图",
            "message": "项目按启动、建设、集成、上线和优化阶段推进。",
            "bullets": [
                "包含启动、调研、知识库建设、AI配置训练、系统集成、联调测试、试点上线、全量推广、运营优化。"
            ],
            "layout": "gantt-plan",
            "visual": "规整甘特图，横轴为项目阶段，纵轴为九项工作包。",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    contract = json.loads(scaffold.stdout)
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    slide = deck["slides"][0]
    assert slide["layout_id"] == "table-data-v1"
    assert slide["props"]["variant"] == "gantt"
    assert len(slide["props"]["rows"]) == 9
    assert contract["authoring_rules"]["outline_policy"]["pages"][0][
        "expected_visual_item_count"
    ] == 9

    patch_path = tmp_path / "deck.patch.json"
    rows = [
        ["启动", "■", "", "", "", ""],
        ["调研", "■", "", "", "", ""],
        ["知识库建设", "", "■", "", "", ""],
        ["AI配置训练", "", "■", "", "", ""],
        ["系统集成", "", "", "■", "", ""],
        ["联调测试", "", "", "■", "", ""],
        ["试点上线", "", "", "", "■", ""],
        ["全量推广", "", "", "", "■", ""],
        ["运营优化", "", "", "", "", "■"],
    ]
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "实施计划与里程碑甘特图",
                            "columns": [
                                "工作包",
                                "启动调研",
                                "建设配置",
                                "集成测试",
                                "上线推广",
                                "运营优化",
                            ],
                            "rows": rows,
                            "variant": "ledger",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert applied.returncode == 0, applied.stdout + applied.stderr
    applied_payload = json.loads(applied.stdout)
    assert any(
        "replaced empty schedule/table cell with an em dash" in item
        for item in applied_payload["normalization_changes"]
    )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    props = deck["slides"][0]["props"]
    assert props["variant"] == "gantt"
    assert len(props["columns"]) == 6
    assert len(props["rows"]) == 9
    assert props["rows"][0] == ["启动", "■", "—", "—", "—", "—"]

    html_path = tmp_path / "index.html"
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    html = html_path.read_text(encoding="utf-8")
    assert "table-gantt" in html
    assert "table-columns-6" in html
    assert "gantt-active" in html
    assert "gantt-idle" in html


def test_bound_deck_rejects_visual_cardinality_and_missing_persisted_intent(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    outline["slides"][0].update(
        {
            "title": "三段能力路径",
            "message": "三个阶段共同形成能力闭环。",
            "layout": "cards",
            "visual": "三段式能力路径",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "title": outline["slides"][0]["title"],
            "subtitle": outline["slides"][0]["message"],
            "items": [
                {"kicker": str(index), "title": f"阶段 {index}", "body": "说明"}
                for index in range(1, 5)
            ],
        }
    )
    deck["slides"][0].pop("outline_intent")
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_spec.js", str(deck_path))

    assert result.returncode == 1
    assert "outline_intent: required by deck contract v2" in result.stdout
    assert "outline visual explicitly requests 3 visual item(s), got 4" in result.stdout


def test_controlled_redesign_preserves_outline_intent_and_previous_layout_draft(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    before = json.loads(deck_path.read_text(encoding="utf-8"))
    redesign_path = tmp_path / "deck.redesign.json"
    redesign_path.write_text(
        json.dumps(
            {
                "theme_id": "soft-editorial",
                "design": {"family": "editorial-spread"},
                "slides": {
                    "slide-01": {
                        "layout_id": "timeline-horizontal-v1",
                        "props": {
                            "eyebrow": "路径",
                            "title": outline["slides"][0]["title"],
                            "subtitle": outline["slides"][0]["message"],
                            "steps": [
                                {"phase": "01", "title": "第一步", "body": "支持点甲"},
                                {"phase": "02", "title": "第二步", "body": "支持点乙"},
                                {"phase": "03", "title": "第三步", "body": "形成闭环"},
                            ],
                            "variant": "staggered",
                        },
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run(
        "apply_deck_redesign.js",
        str(deck_path),
        str(redesign_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    after = json.loads(deck_path.read_text(encoding="utf-8"))
    assert after["theme_id"] == "soft-editorial"
    assert after["design"]["family"] == "editorial-spread"
    slide = after["slides"][0]
    assert slide["layout_id"] == "timeline-horizontal-v1"
    assert slide["outline_intent"] == before["slides"][0]["outline_intent"]
    assert slide["layout_drafts"]["cards-grid-v1"] == before["slides"][0]["props"]
    contract = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert contract["contract_version"] == 2
    assert contract["theme_id"] == "soft-editorial"
    assert contract["layout_plan"] == ["timeline-horizontal-v1"]
    manifest = json.loads(
        (tmp_path / "assets" / "generated" / "manifest.json").read_text()
    )
    assert manifest["deck"]["theme_id"] == "soft-editorial"
    validation = _run("validate_deck_spec.js", str(deck_path))
    assert validation.returncode == 0, validation.stdout + validation.stderr


def test_bound_deck_spec_requires_outline_page_title_and_support_copy(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(outline_path)
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "cards-grid-v1",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    for slide, outline_slide in zip(deck["slides"], outline["slides"], strict=True):
        slide["props"]["title"] = outline_slide["title"]
        slide["props"]["subtitle"] = outline_slide["message"]
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    valid = _run("validate_deck_spec.js", str(deck_path))
    assert valid.returncode == 0, valid.stdout + valid.stderr
    assert json.loads(valid.stdout.split("\nDeck spec validation", 1)[0])[
        "outlineBinding"
    ]["required"] is True

    deck["slides"][1].pop("source_outline_page")
    deck["slides"][1]["props"]["title"] = "被替换的页面"
    deck["slides"][1]["props"]["subtitle"] = "正文也偏离了原大纲"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    invalid = _run("validate_deck_spec.js", str(deck_path))

    assert invalid.returncode == 1
    assert "slides.slide-02.source_outline_page" in invalid.stdout
    assert "must include outline page 2 title" in invalid.stdout
    assert "must preserve at least one exact message/bullet" in invalid.stdout


def test_bound_deck_spec_accepts_labeled_outline_bullet_fragment(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    outline["slides"][0].update(
        {
            "title": "Q2 客服效率改进复盘",
            "message": "本次复盘覆盖问题、行动、结果和下一步。",
            "bullets": ["副标题：从响应提速到一次解决率提升"],
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "title": "Q2 客服效率改进复盘",
            "subtitle": "从响应提速到一次解决率提升",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_spec.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_bound_deck_spec_accepts_labeled_actions_as_timeline_titles(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    outline["slides"][0].update(
        {
            "title": "采取的行动",
            "message": "三项行动形成客服改进闭环。",
            "bullets": [
                "统一知识库：沉淀标准答案与处理口径",
                "工单自动分流：提升分配效率",
                "每周质检复盘：持续推动流程修正",
            ],
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "timeline-horizontal-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "title": "采取的行动",
            "subtitle": "",
            "steps": [
                {"phase": "知识库", "title": "统一知识库", "body": ""},
                {"phase": "工单", "title": "工单自动分流", "body": ""},
                {"phase": "质检", "title": "每周质检复盘", "body": ""},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_spec.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_bound_deck_spec_accepts_quantitative_copy_split_across_kpi_fields(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    outline["slides"][0].update(
        {
            "title": "改进前问题",
            "message": "改进前客服链路包含三项指标。",
            "bullets": [
                "首次响应时间为 18 分钟。",
                "一次解决率为 68%。",
                "满意度为 4.2/5。",
            ],
            "evidence": [],
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "kpi-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "title": "改进前问题",
            "items": [
                {"label": "首次响应时间", "value": "18 分钟", "detail": "", "delta": ""},
                {"label": "一次解决率", "value": "68%", "detail": "", "delta": ""},
                {"label": "满意度", "value": "4.2/5", "detail": "", "delta": ""},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_spec.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_strict_source_patch_keeps_percent_chart_values_from_rate_category(
    tmp_path: Path,
) -> None:
    source_fact = (
        "首次响应时间从 18 分钟降到 7 分钟；"
        "一次解决率从 68% 提升到 81%；"
        "满意度从 4.2/5 提升到 4.6/5。"
    )
    source_text = f"改进结果：{source_fact}不补充任何我未提供的事实。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        source_fact,
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "改进结果",
                            "categories": ["首次响应时间", "一次解决率", "满意度"],
                            "series": [
                                {"name": "改进前", "values": ["18", "68", "4.2"]},
                                {"name": "改进后", "values": ["7", "81", "4.6"]},
                            ],
                            "insight": source_fact,
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["props"]["series"][0]["values"] == ["18", "68", "4.2"]
    assert deck["slides"][0]["props"]["series"][1]["values"] == ["7", "81", "4.6"]
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr


def test_strict_source_sanitizer_removes_production_directives_from_slide_copy(
    tmp_path: Path,
) -> None:
    source_fact = (
        "首次响应时间从 18 分钟降到 7 分钟；"
        "一次解决率从 68% 提升到 81%。"
    )
    source_text = (
        f"制作一份 5 页复盘。改进结果：{source_fact}"
        "必须使用可编辑图表呈现前后对比；全部为可编辑文字、图表和形状。"
        "不补充任何我未提供的事实。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-editorial-v1",
        "chart-data-v1",
        "--fact",
        "5 页复盘",
        "--fact",
        source_fact,
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "内部项目复盘",
                            "subtitle": "待补充",
                            "meta": "5 页复盘｜全部为可编辑文字、图表和形状",
                        }
                    },
                    "slide-02": {
                        "props": {
                            "title": "改进结果",
                            "subtitle": "结果展示必须使用可编辑图表呈现前后对比",
                            "categories": ["首次响应时间", "一次解决率"],
                            "series": [
                                {"name": "改进前", "values": ["18", "68%"]},
                                {"name": "改进后", "values": ["7", "81%"]},
                            ],
                            "insight": source_fact,
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    slides = json.loads(deck_path.read_text(encoding="utf-8"))["slides"]
    assert slides[0]["props"]["meta"] == "5 页复盘"
    assert slides[1]["props"]["subtitle"] == ""
    assert slides[1]["props"]["insight"] == source_fact


def test_deck_spec_rejects_chart_placeholder_as_data(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        "一次解决率从 68% 提升到 81%",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"]["series"][0]["values"][1] = "待补充"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_spec.js", str(deck_path))

    assert result.returncode == 1
    assert "placeholders are not valid data" in result.stdout


def test_strict_source_kpi_sanitizer_uses_local_fact_fragments(
    tmp_path: Path,
) -> None:
    source_fact = "第2页 改进前问题：首次响应时间 18 分钟；一次解决率 68%；满意度 4.2/5。"
    source_text = f"改进前问题：{source_fact}不补充任何我未提供的事实。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "kpi-grid-v1",
        "--fact",
        source_fact,
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "改进前问题",
                            "subtitle": "问题链路表达为响应慢、解决不充分、体验受影响。",
                            "items": [
                                {"label": "首次响应时间", "value": "18 分钟", "detail": "体现等待偏长", "delta": "响应慢"},
                                {"label": "一次解决率", "value": "68%", "detail": "说明解决不充分", "delta": "解决不充分"},
                                {"label": "满意度", "value": "4.2/5", "detail": "反映体验受影响", "delta": "体验受影响"},
                            ],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    props = deck["slides"][0]["props"]
    assert props["subtitle"] == "首次响应时间 → 一次解决率 → 满意度"
    assert [item["detail"] for item in props["items"]] == [
        "首次响应时间 18 分钟",
        "一次解决率 68%",
        "满意度 4.2/5",
    ]
    assert [item["delta"] for item in props["items"]] == ["", "", ""]
    assert "待补充" not in json.dumps(props, ensure_ascii=False)


def test_strict_source_table_sanitizer_drops_unsupported_optional_column(
    tmp_path: Path,
) -> None:
    source_facts = [
        "补齐高频问题知识库",
        "优化分流规则",
        "建立月度复盘机制",
        "执行角色为产品、客服运营、数据分析",
        "成员姓名未提供",
    ]
    source_text = "；".join(source_facts) + "。不补充任何我未提供的事实。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold_args = ["inspect_deck_contract.js", "table-data-v1"]
    for fact in source_facts:
        scaffold_args.extend(["--fact", fact])
    scaffold_args.extend(["--out", str(deck_path)])
    scaffold = _run(*scaffold_args, env=env)
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "下一步",
                            "subtitle": "下一阶段继续推动三项工作形成闭环。",
                            "columns": ["推进事项", "执行角色", "角色职责", "成员姓名"],
                            "rows": [
                                ["补齐高频问题知识库", "产品", "补齐相关产品信息和口径", "姓名未提供"],
                                ["优化分流规则", "客服运营", "推动执行落地", "姓名未提供"],
                                ["建立月度复盘机制", "数据分析", "完善指标跟踪", "姓名未提供"],
                            ],
                            "source": "成员姓名未提供",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    props = deck["slides"][0]["props"]
    assert props["subtitle"] == ""
    assert props["columns"] == ["推进事项", "执行角色", "成员姓名"]
    assert props["rows"] == [
        ["补齐高频问题知识库", "产品", "姓名未提供"],
        ["优化分流规则", "客服运营", "姓名未提供"],
        ["建立月度复盘机制", "数据分析", "姓名未提供"],
    ]
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr


def test_strict_source_table_sanitizer_drops_duplicate_column(
    tmp_path: Path,
) -> None:
    source_facts = [
        "补齐高频问题知识库",
        "优化分流规则",
        "建立月度复盘机制",
        "执行角色为产品、客服运营、数据分析",
        "成员姓名未提供",
    ]
    source_text = "；".join(source_facts) + "。不补充任何我未提供的事实。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold_args = ["inspect_deck_contract.js", "table-data-v1"]
    for fact in source_facts:
        scaffold_args.extend(["--fact", fact])
    scaffold_args.extend(["--out", str(deck_path)])
    scaffold = _run(*scaffold_args, env=env)
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "下一步",
                            "columns": ["下一步事项", "执行角色", "角色职责", "成员姓名"],
                            "rows": [
                                ["补齐高频问题知识库", "产品", "补齐高频问题知识库", "姓名未提供"],
                                ["优化分流规则", "客服运营", "优化分流规则", "姓名未提供"],
                                ["建立月度复盘机制", "数据分析", "建立月度复盘机制", "姓名未提供"],
                            ],
                            "source": "成员姓名未提供",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    props = deck["slides"][0]["props"]
    assert props["columns"] == ["下一步事项", "执行角色", "成员姓名"]
    assert props["rows"] == [
        ["补齐高频问题知识库", "产品", "姓名未提供"],
        ["优化分流规则", "客服运营", "姓名未提供"],
        ["建立月度复盘机制", "数据分析", "姓名未提供"],
    ]


def test_scaffold_normalizes_structured_next_steps_closing_to_table(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    outline["slides"][0].update(
        {
            "title": "下一步",
            "message": "展示下一步、执行角色和成员姓名状态。",
            "bullets": [
                "补齐高频问题知识库",
                "执行角色为产品、客服运营、数据分析",
                "成员姓名未提供",
            ],
            "layout": "下一步行动与角色职责",
            "visual": "用职责矩阵展示任务、角色和姓名状态。",
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "closing-next-steps-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["layout_id"] == "table-data-v1"
    report = json.loads(
        (tmp_path / "qa" / "deck_contract.json").read_text(encoding="utf-8")
    )
    assert report["layout_plan_requested"] == ["closing-next-steps-v1"]
    assert report["layout_plan"] == ["table-data-v1"]
    assert report["layout_normalizations"] == [
        {
            "slide": 1,
            "from": "closing-next-steps-v1",
            "to": "table-data-v1",
            "reason": "outline requires parallel next-step, role/owner, and identity fields",
        }
    ]


def test_scaffold_normalizes_five_item_closing_summary_to_cards(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    outline["slides"][0].update(
        {
            "title": "合作价值与评标结论",
            "message": "用评标价值收束整套方案。",
            "bullets": [
                "理解业务",
                "技术可信",
                "集成清晰",
                "实施可控",
                "投入产出清晰",
            ],
            "layout": "closing-next-steps-v1",
            "visual": (
                "结论页，用五项评标价值条目收束：理解业务、技术可信、"
                "集成清晰、实施可控、投入产出清晰。"
            ),
        }
    )
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )
    deck_path = tmp_path / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "closing-next-steps-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["layout_id"] == "cards-grid-v1"
    report = json.loads(
        (tmp_path / "qa" / "deck_contract.json").read_text(encoding="utf-8")
    )
    assert report["layout_plan_requested"] == ["closing-next-steps-v1"]
    assert report["layout_plan"] == ["cards-grid-v1"]
    assert report["layout_normalizations"] == [
        {
            "slide": 1,
            "from": "closing-next-steps-v1",
            "to": "cards-grid-v1",
            "reason": (
                "outline requests 5 closing value items, "
                "which exceeds the four-action closing layout"
            ),
        }
    ]


def test_strict_source_closing_sanitizer_removes_unsupported_action_expansion(
    tmp_path: Path,
) -> None:
    source_facts = [
        "下一步",
        "优化分流规则",
        "执行角色为产品",
        "成员姓名未提供",
    ]
    source_text = "；".join(source_facts) + "。不补充任何我未提供的事实。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold_args = ["inspect_deck_contract.js", "closing-next-steps-v1"]
    for fact in source_facts:
        scaffold_args.extend(["--fact", fact])
    scaffold_args.extend(["--out", str(deck_path)])
    scaffold = _run(*scaffold_args, env=env)
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "eyebrow": "下一步",
                            "title": "下一步",
                            "subtitle": "推动所有工作形成闭环。",
                            "actions": [
                                {
                                    "label": "产品｜姓名未提供",
                                    "detail": "优化分流规则，明确规则调整与落地职责。",
                                }
                            ],
                            "contact": "成员姓名未提供",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    serialized = json.dumps(deck["slides"][0]["props"], ensure_ascii=False)
    assert "明确规则调整与落地职责" not in serialized
    assert "推动所有工作形成闭环" not in serialized
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr


def test_batch_patch_restores_bound_outline_title(tmp_path: Path) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=1,
        source_mode="user_provided",
    )
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "--outline",
        str(outline_path),
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "被模型改写的标题",
                            "subtitle": outline["slides"][0]["message"],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert applied.returncode == 0, applied.stdout + applied.stderr
    payload = json.loads(applied.stdout)
    assert (
        "slides.slide-01.props.title: restored bound outline page title"
        in payload["normalization_changes"]
    )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["props"]["title"] == outline["slides"][0]["title"]


def test_source_bound_patch_guard_recognizes_no_unprovided_facts_wording(
    tmp_path: Path,
) -> None:
    source_text = (
        "制作一页客服效率复盘。首次响应时间 18 分钟。"
        "不补充任何我未提供的事实。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--fact",
        "首次响应时间 18 分钟",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "2024 年成立",
                            "subtitle": "首次响应时间 18 分钟",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    payload = json.loads(applied.stdout)
    assert payload["truth_guard_changes"]
    assert "2024" not in deck_path.read_text(encoding="utf-8")
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr
    truth_payload = json.loads(truth.stdout.split("\nDeck truth validation:", 1)[0])
    assert truth_payload["sourceBinding"]["strict"] is True


def test_strict_source_patch_preserves_user_provided_action_titles(
    tmp_path: Path,
) -> None:
    source_text = (
        "采取的行动：统一知识库、工单自动分流、每周质检复盘。"
        "不补充任何我未提供的事实。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "timeline-horizontal-v1",
        "--fact",
        "采取的行动：统一知识库、工单自动分流、每周质检复盘。",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "采取的行动",
                            "subtitle": "不补充未提供事实",
                            "steps": [
                                {"phase": "01", "title": "统一知识库", "body": "待补充"},
                                {"phase": "02", "title": "工单自动分流", "body": "待补充"},
                                {"phase": "03", "title": "每周质检复盘", "body": "待补充"},
                            ],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert [step["title"] for step in deck["slides"][0]["props"]["steps"]] == [
        "统一知识库",
        "工单自动分流",
        "每周质检复盘",
    ]


def test_truth_validator_accepts_compound_copy_of_exact_source_facts(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        "首次响应时间从 18 分钟降到 7 分钟",
        "--fact",
        "一次解决率从 68% 提升到 81%",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "前后对比",
            "title": "改进结果",
            "subtitle": "两项指标前后对比",
            "chart_type": "column",
            "categories": ["首次响应时间", "一次解决率"],
            "series": [
                {"name": "改进前", "values": ["18", "68%"]},
                {"name": "改进后", "values": ["7", "81%"]},
            ],
            "insight": (
                "首次响应时间从 18 分钟降到 7 分钟；"
                "一次解决率从 68% 提升到 81%。"
            ),
            "source": "",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("layout_id", "expected_slot"),
    [
        ("cover-hero-v1", "hero"),
        ("cover-editorial-v1", "background"),
    ],
)
def test_creative_image_mode_scaffolds_a_required_cover_generation(
    tmp_path: Path,
    layout_id: str,
    expected_slot: str,
) -> None:
    deck_path = tmp_path / f"{layout_id}.json"

    result = _run(
        "inspect_deck_contract.js",
        layout_id,
        "--image-mode",
        "creative_image_mode",
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (tmp_path / "assets" / "generated" / "manifest.json").read_text()
    )
    assert manifest["mode"] == "creative_image_mode"
    assert manifest["image_plan"][0]["slot"] == expected_slot
    assert manifest["image_plan"][0]["required"] is True
    assert manifest["image_plan"][0]["decision"] == "generate"
    assert manifest["image_plan"][0]["status"] == "pending"
    assert manifest["image_plan"][0]["output_path"].endswith(
        f"slide-01-{expected_slot}.png"
    )


def test_auto_image_mode_promotes_investor_pitch_cover_to_generation(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--title",
        "AI 质检平台融资路演",
        "--image-mode",
        "auto",
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (tmp_path / "assets" / "generated" / "manifest.json").read_text()
    )
    cover = manifest["image_plan"][0]
    assert cover["slot"] == "hero"
    assert cover["required"] is True
    assert cover["decision"] == "generate"
    assert cover["status"] == "pending"
    assert "investor/pitch/launch" in cover["decision_reason"]


def test_auto_image_mode_promotes_visual_story_cover_to_generation(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--title",
        "内马尔巴萨传奇故事",
        "--image-mode",
        "auto",
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (tmp_path / "assets" / "generated" / "manifest.json").read_text()
    )
    cover = manifest["image_plan"][0]
    assert cover["required"] is True
    assert cover["decision"] == "generate"
    assert "visual story" in cover["decision_reason"]


def test_auto_image_mode_respects_explicit_image_opt_out(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--title",
        "内马尔巴萨传奇故事，不要生成图片",
        "--image-mode",
        "auto",
        "--out",
        str(deck_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(
        (tmp_path / "assets" / "generated" / "manifest.json").read_text()
    )
    cover = manifest["image_plan"][0]
    assert cover["required"] is False
    assert cover["decision"] == "skip"


def test_scaffold_copies_and_validates_user_supplied_image_asset(
    tmp_path: Path,
) -> None:
    source = tmp_path / "client-ui.png"
    source.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
            "/x8AAusB9Wl2YvQAAAAASUVORK5CYII="
        )
    )
    deck_path = tmp_path / "deck" / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--image-mode",
        "auto",
        "--image-asset",
        f"1:hero={source}",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    manifest_path = deck_path.parent / "assets" / "generated" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cover = manifest["image_plan"][0]
    assert cover["decision"] == "use_existing"
    assert cover["status"] == "ready"
    assert cover["origin"] == "uploaded"
    assert cover["output_path"] == "assets/source/slide-01-hero.png"
    copied = deck_path.parent / cover["output_path"]
    assert copied.read_bytes() == source.read_bytes()

    unbound = _run(
        "validate_image_manifest.js",
        str(manifest_path),
        "--deck",
        str(deck_path),
    )
    assert unbound.returncode == 1
    assert "planned image asset is not referenced by deck.json" in unbound.stdout

    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"]["hero"] = {
        "src": cover["output_path"],
        "alt": "用户提供的客户端界面",
        "origin": "uploaded",
    }
    deck_path.write_text(
        json.dumps(deck, ensure_ascii=False),
        encoding="utf-8",
    )
    report_path = deck_path.parent / "qa" / "image_manifest.json"
    validated = _run(
        "validate_image_manifest.js",
        str(manifest_path),
        "--deck",
        str(deck_path),
        "--report",
        str(report_path),
    )

    assert validated.returncode == 0, validated.stdout + validated.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["successfulGeneratedCount"] == 0
    assert report["successfulExistingCount"] == 1


def test_deck_contract_normalizes_observed_model_layout_aliases(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "manifesto-v1",
        "kpi-grid-v1",
        "project-case-study-v1",
        "clients-logo-grid-v1",
        "awards-press-v1",
        "team-showcase-v1",
        "timeline-horizontal-v1",
        "closing-v2",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text())
    assert [slide["layout_id"] for slide in deck["slides"]] == [
        "cover-hero-v1",
        "statement-focus-v1",
        "kpi-grid-v1",
        "project-case-study-v1",
        "cards-grid-v1",
        "cards-grid-v1",
        "cards-grid-v1",
        "timeline-horizontal-v1",
        "closing-next-steps-v1",
    ]

    inspected = _run("inspect_layout.js", "team-showcase-v1")
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["id"] == "cards-grid-v1"


def test_deck_contract_normalizes_pitch_layout_and_required_field_aliases(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"

    scaffold = _run(
        "inspect_deck_contract.js",
        "problem-solution-v1",
        "process-flow-v1",
        "business-model-v1",
        "comparison-matrix-v1",
        "funding-use-v1",
        "--require-field",
        "3:cards",
        "--require-field",
        "4:matrix",
        "--require-field",
        "5:chart",
        "--out",
        str(deck_path),
    )

    assert scaffold.returncode == 0, scaffold.stderr
    assert len(scaffold.stdout) < 22_750
    deck = json.loads(deck_path.read_text())
    assert [slide["layout_id"] for slide in deck["slides"]] == [
        "comparison-two-column-v1",
        "timeline-horizontal-v1",
        "cards-grid-v1",
        "table-data-v1",
        "chart-data-v1",
    ]
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["required_fields"] == [
        {"slide": 3, "field": "items"},
        {"slide": 4, "field": "rows"},
        {"slide": 5, "field": "series"},
    ]
    assert report["required_field_normalizations"] == [
        {"slide": 3, "from": "cards", "to": "items"},
        {"slide": 4, "from": "matrix", "to": "rows"},
        {"slide": 5, "from": "chart", "to": "series"},
    ]


@pytest.mark.parametrize(
    ("requested", "canonical"),
    [
        ("statement-large-v1", "statement-focus-v1"),
        ("creative-team-v2", "cards-grid-v1"),
        ("client-logo-wall-v1", "cards-grid-v1"),
        ("portfolio-showcase-v2", "project-case-study-v1"),
        ("process-roadmap-v2", "timeline-horizontal-v1"),
        ("metrics-dashboard-v2", "kpi-grid-v1"),
        ("versus-split-v2", "comparison-two-column-v1"),
        ("chapter-divider-v2", "section-marker-v1"),
        ("opening-title-v2", "cover-hero-v1"),
        ("visual-split-v2", "image-hero-split-v1"),
        ("ranking-bar-chart-v2", "chart-bar-v1"),
        ("revenue-line-chart-v2", "chart-data-v1"),
        ("market-donut-chart-v2", "chart-data-v1"),
        ("feature-matrix-v2", "table-data-v1"),
        ("research-deep-dive-v2", "text-columns-v1"),
        ("architecture-diagram-v1", "architecture-layered-v1"),
        ("integration-map-v1", "system-integration-v1"),
        ("qualitative-dashboard-v1", "dashboard-overview-v1"),
        ("thank-you-v2", "closing-next-steps-v1"),
    ],
)
def test_inspect_layout_normalizes_semantic_aliases(
    requested: str,
    canonical: str,
) -> None:
    inspected = _run("inspect_layout.js", requested)

    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["id"] == canonical


def test_deck_contract_rejects_layout_missing_required_page_field(tmp_path: Path) -> None:
    rejected = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "image-hero-split-v1",
        "--require-field",
        "2:metrics",
        "--out",
        str(tmp_path / "rejected.json"),
    )
    accepted = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "project-case-study-v1",
        "--require-field",
        "2:metrics",
        "--out",
        str(tmp_path / "accepted.json"),
    )

    assert rejected.returncode == 1
    assert "does not provide required field metrics" in rejected.stderr
    assert accepted.returncode == 0, accepted.stderr
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["required_fields"] == [{"slide": 2, "field": "metrics"}]


def test_strict_source_binding_rejects_derived_or_paraphrased_facts(
    tmp_path: Path,
) -> None:
    source_text = (
        "工作室：NOON Studio，2026 年是第三年。"
        "业务是品牌视觉 + 数字产品设计；今年交付 28 个项目。"
        "只使用我提供的事实，禁止虚构。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    rejected_path = tmp_path / "rejected.json"

    rejected = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--fact",
        "NOON Studio 成立于 2024 年，2026 年是第三年",
        "--fact",
        "业务方向：品牌视觉 + 数字产品设计",
        "--out",
        str(rejected_path),
        env=env,
    )

    assert rejected.returncode == 1
    assert "Source fact binding failed" in rejected.stderr
    assert "成立于 2024 年" in rejected.stderr
    assert "contiguous phrase" in rejected.stderr
    assert not rejected_path.exists()

    accepted_path = tmp_path / "accepted.json"
    accepted = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--fact",
        "NOON Studio",
        "--fact",
        "2026 年是第三年",
        "--fact",
        "品牌视觉 + 数字产品设计",
        "--fact",
        "今年交付 28 个项目",
        "--out",
        str(accepted_path),
        env=env,
    )

    assert accepted.returncode == 0, accepted.stderr
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["source_binding"]["strict"] is True
    assert report["source_binding"]["verified_fact_count"] == 4


def test_strict_source_binding_restores_exact_source_after_safe_copy_drift(
    tmp_path: Path,
) -> None:
    source_text = (
        "首次响应时间从 18 分钟降至 7 分钟，一次解决率从 68% 提升到 81%。"
        "不补充任何我未提供的事实。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    copied_with_drift = "一次解决率从 68% 提升到 7 分钟"

    result = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        copied_with_drift,
        "--out",
        str(deck_path),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["truth_contract"]["source_facts"] == [source_text]
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["source_binding"]["verified_fact_count"] == 1
    assert report["source_fact_normalizations"] == [
        {
            "from": copied_with_drift,
            "to": source_text,
            "reason": "restored exact runtime source text after a non-numeric copy drift",
        }
    ]

    unrelated_path = tmp_path / "unrelated.json"
    unrelated = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        "这是业内最领先的客服体系",
        "--out",
        str(unrelated_path),
        env=env,
    )
    assert unrelated.returncode == 1
    assert "Source fact binding failed" in unrelated.stderr
    assert not unrelated_path.exists()


def test_researched_facts_are_scaffolded_separately_from_user_source(
    tmp_path: Path,
) -> None:
    source_text = "制作一个关于内马尔巴萨传奇故事的 ppt"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--research-fact",
        "Neymar joined FC Barcelona in 2013.",
        "--research-fact",
        "FC Barcelona won the treble in the 2014/15 season.",
        "--out",
        str(deck_path),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text())
    assert deck["truth_contract"] == {
        "mode": "source_bound",
        "source_facts": [],
        "research_facts": [
            "Neymar joined FC Barcelona in 2013.",
            "FC Barcelona won the treble in the 2014/15 season.",
        ],
        "assumptions": [],
    }
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["source_fact_count"] == 0
    assert report["research_fact_count"] == 2
    assert report["source_binding"]["verified_fact_count"] == 0

    validated = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert validated.returncode == 0, validated.stdout + validated.stderr
    truth_report = json.loads(validated.stdout.split("\nDeck truth validation:", 1)[0])
    assert truth_report["researchFactCount"] == 2


def test_number_backing_keeps_cjk_comma_separated_date_and_year_tokens() -> None:
    if NODE is None:
        pytest.skip("Node.js is required to test the controlled deck compiler")
    fact = "出生于 2007-07-13，2014 年以 7 岁加入 FC Barcelona"
    script = (
        f"const truth=require({json.dumps(str(SCRIPTS_DIR / 'validate_deck_truth.js'))});"
        f"const facts=[{json.dumps(fact, ensure_ascii=False)}];"
        "console.log(JSON.stringify(["
        "truth.isNumberSourceBacked('13', facts),"
        "truth.isNumberSourceBacked('2014', facts)"
        "]));"
    )

    result = subprocess.run(
        [str(NODE), "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == [True, True]


def test_public_research_deck_accepts_source_preserving_award_paraphrases(
    tmp_path: Path,
) -> None:
    source_text = "制作一套介绍拉明·亚马尔的 PPT"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    research_facts = [
        (
            "UEFA 报道 Lamine Yamal 随西班牙赢得 EURO 2024，并获 "
            "Young Player of the Tournament"
        ),
        "EURO 2024 决赛在其 17 岁生日后一天",
    ]
    deck_path = tmp_path / "deck.json"
    scaffold_args = ["inspect_deck_contract.js", "cards-grid-v1"]
    for fact in research_facts:
        scaffold_args.extend(["--research-fact", fact])
    scaffold_args.extend(["--out", str(deck_path)])
    scaffold = _run(*scaffold_args, env=env)
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr

    items = [
        {
            "kicker": "01",
            "title": "西班牙夺冠成员",
            "body": "UEFA 报道称，亚马尔随西班牙赢得 EURO 2024。",
        },
        {
            "kicker": "02",
            "title": "最佳年轻球员",
            "body": "UEFA 报道称，他被评为 Young Player of the Tournament。",
        },
        {
            "kicker": "03",
            "title": "决赛节点",
            "body": "决赛发生在其 17 岁生日后一天。",
        },
    ]
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "国家队与欧洲杯突破",
                            "subtitle": "纪录进入冠军叙事",
                            "items": items,
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["props"]["items"] == items
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr


def test_public_research_deck_accepts_supported_chinese_result_paraphrase(
    tmp_path: Path,
) -> None:
    source_text = "制作一套4页介绍西班牙夺得2026世界杯的ppt"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    research_fact = (
        "西班牙1:0击败阿根廷，时隔16年再次捧杯；"
        "队史第二座世界杯冠军 | 中国新闻网"
    )
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "statement-focus-v1",
        "--research-fact",
        research_fact,
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    proof = {
        "value": "第二座",
        "label": "西班牙再次赢得世界杯，队史冠军数来到第二座。",
    }
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "statement": "历史意义：16年后再捧世界杯",
                            "support": "西班牙时隔16年再次夺冠。",
                            "proofs": [proof],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["props"]["proofs"] == [proof]
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr


def test_public_research_patch_omits_only_unsupported_optional_proof(
    tmp_path: Path,
) -> None:
    source_text = "制作一套4页介绍西班牙夺得2026世界杯的ppt"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "statement-focus-v1",
        "--research-fact",
        "西班牙1:0击败阿根廷，时隔16年再次捧杯；队史第二座世界杯冠军",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    supported = {
        "value": "第二座",
        "label": "西班牙再次赢得世界杯，队史冠军数来到第二座。",
    }
    unsupported = [
        {"value": "错误对手", "label": "阿根廷赢得世界杯。"},
        {"value": "错误赛事", "label": "西班牙赢得欧洲杯冠军。"},
    ]
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "statement": "历史意义：16年后再捧世界杯",
                            "support": "西班牙时隔16年再次夺冠。",
                            "proofs": [supported, *unsupported],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    payload = json.loads(applied.stdout)
    assert (
        "slides.slide-01.props.proofs.1: omitted unsupported optional research proof"
        in payload["truth_guard_changes"]
    )
    assert len(payload["truth_guard_changes"]) == 2
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["props"]["proofs"] == [supported]


def test_public_research_deck_accepts_generic_award_heading_and_synthesis(
    tmp_path: Path,
) -> None:
    source_text = "制作一套介绍拉明·亚马尔的 PPT"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    research_facts = [
        "2024 Kopa Trophy; 21岁以下 | FC Barcelona",
        "2024 Golden Boy | FC Barcelona",
        "2023 Golden Boy The Youngest | FC Barcelona",
    ]
    deck_path = tmp_path / "deck.json"
    scaffold_args = ["inspect_deck_contract.js", "cards-grid-v1"]
    for fact in research_facts:
        scaffold_args.extend(["--research-fact", fact])
    scaffold_args.extend(["--out", str(deck_path)])
    scaffold = _run(*scaffold_args, env=env)
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr

    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "已获奖项与可信总结",
                            "subtitle": "公开记录构成外部认可。",
                            "items": [
                                {
                                    "kicker": "2024",
                                    "title": "Kopa Trophy",
                                    "body": "2024 Kopa Trophy; 21岁以下",
                                },
                                {
                                    "kicker": "2024",
                                    "title": "Golden Boy",
                                    "body": "2024 Golden Boy",
                                },
                                {
                                    "kicker": "2023",
                                    "title": "Golden Boy The Youngest",
                                    "body": "2023 Golden Boy The Youngest",
                                },
                                {
                                    "kicker": "总结",
                                    "title": "可信定位",
                                    "body": (
                                        "以官方纪录、冠军经历和已获奖项支撑其青年代表"
                                        "人物形象。"
                                    ),
                                },
                            ],
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr


def test_apply_patch_flattens_nested_background_image_object(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    generated = tmp_path / "assets" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "cover.png").write_bytes(b"image")
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "background": {
                            "image": {
                                "src": "assets/generated/cover.png",
                                "alt": "球场氛围概念图",
                            },
                            "treatment": "wash-light",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    result = json.loads(applied.stdout)
    assert (
        "slides.slide-01.background.image: flattened nested media object"
        in result["normalization_changes"]
    )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["background"] == {
        "src": "assets/generated/cover.png",
        "alt": "球场氛围概念图",
        "origin": "generated",
        "fit": "cover",
        "position": "center",
        "treatment": "wash-light",
    }


def test_strict_source_request_rejects_researched_facts(tmp_path: Path) -> None:
    source_text = "只使用我提供的事实，禁止虚构：内马尔。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--fact",
        "内马尔",
        "--research-fact",
        "Neymar joined FC Barcelona in 2013.",
        "--out",
        str(tmp_path / "deck.json"),
        env=env,
    )

    assert result.returncode == 1
    assert "Research fact binding failed" in result.stderr
    assert "strict source-only request" in result.stderr


def test_source_fact_binding_ignores_editorial_whitespace(tmp_path: Path) -> None:
    source_text = (
        "产品为面向 中小制造工厂 的 AI 质检 + 智能排产平台。"
        "已有 30 家试点客户。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--fact",
        "产品为面向中小制造工厂的 AI 质检 + 智能排产平台。",
        "--fact",
        "已有30家试点客户",
        "--out",
        str(deck_path),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["source_binding"]["verified_fact_count"] == 2


def test_strict_source_binding_strips_model_added_fact_labels(tmp_path: Path) -> None:
    source_text = (
        "工作室叫 NOON Studio。业务是品牌视觉 + 数字产品设计。"
        "只使用我提供的事实，禁止虚构。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"

    result = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--fact",
        "工作室名称：NOON Studio",
        "--fact",
        "业务：品牌视觉 + 数字产品设计",
        "--out",
        str(deck_path),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text())
    assert deck["truth_contract"]["source_facts"] == [
        "NOON Studio",
        "品牌视觉 + 数字产品设计",
    ]
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["source_binding"]["verified_fact_count"] == 2
    assert report["source_fact_normalizations"] == [
        {"from": "工作室名称：NOON Studio", "to": "NOON Studio"},
        {"from": "业务：品牌视觉 + 数字产品设计", "to": "品牌视觉 + 数字产品设计"},
    ]


def test_authorized_assumptions_support_disclosed_percent_chart_data(
    tmp_path: Path,
) -> None:
    source_text = (
        "公司名为 ACME。"
        "如涉及未提供的具体数据，请使用合理假设数据，"
        "并在备注中标明为示意 / 假设。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        "ACME",
        "--assumption",
        "服务收入占比假设：咨询 45%、产品 35%、培训 20%",
        "--out",
        str(deck_path),
        env=env,
    )

    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    report = json.loads((tmp_path / "qa" / "deck_contract.json").read_text())
    assert report["assumption_count"] == 1
    assert report["source_binding"]["allows_assumptions"] is True

    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "ACME",
            "title": "服务收入结构",
            "subtitle": "三类业务占比",
            "chart_type": "donut",
            "categories": ["咨询", "产品", "培训"],
            "series": [{"name": "占比", "values": ["45", "35", "20"]}],
            "value_suffix": "%",
            "insight": "咨询业务占比最高",
            "source": "假设数据，仅作示意",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    accepted = _run("validate_deck_truth.js", str(deck_path), env=env)

    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    payload = json.loads(accepted.stdout.split("\nDeck truth validation:", 1)[0])
    assert payload["assumptionCount"] == 1

    deck["slides"][0]["props"]["source"] = ""
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    rejected = _run("validate_deck_truth.js", str(deck_path), env=env)

    assert rejected.returncode == 1
    rejected_payload = json.loads(
        rejected.stdout.split("\nDeck truth validation:", 1)[0]
    )
    assert any("visible 假设/示意 disclosure" in issue for issue in rejected_payload["issues"])


@pytest.mark.parametrize(
    "source_text",
    [
        "公司名为 ACME。请制作一份简介。",
        "公司名为 ACME。不可以使用假设数据。",
        "公司名为 ACME。只使用我提供的事实，禁止虚构。可以使用假设数据。",
    ],
)
def test_assumptions_require_unambiguous_user_permission(
    tmp_path: Path,
    source_text: str,
) -> None:
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")

    result = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        "ACME",
        "--assumption",
        "业务占比假设为 45%",
        "--out",
        str(tmp_path / "deck.json"),
        env=env,
    )

    assert result.returncode == 1
    assert "Assumption binding failed" in result.stderr
    assert "request_user_input" in result.stderr


def test_authorized_assumptions_cannot_be_smuggled_into_source_facts(
    tmp_path: Path,
) -> None:
    source_text = "公司名为 ACME。请使用合理假设数据并标明为示意。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")

    result = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        "ACME 收入增长 45%",
        "--out",
        str(tmp_path / "deck.json"),
        env=env,
    )

    assert result.returncode == 1
    assert "Source fact binding failed" in result.stderr
    assert "contiguous phrase" in result.stderr


def test_batch_patch_can_add_only_authorized_assumptions(
    tmp_path: Path,
) -> None:
    source_text = "公司名为 ACME。请使用合理假设数据并标明为示意。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--fact",
        "ACME",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "truth_contract": {
                    "mode": "illustrative",
                    "source_facts": ["伪造事实"],
                    "assumptions": ["业务占比假设为 45%"],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    patched = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert patched.returncode == 0, patched.stdout + patched.stderr
    deck = json.loads(deck_path.read_text())
    assert deck["truth_contract"] == {
        "mode": "source_bound",
        "source_facts": ["ACME"],
        "assumptions": ["业务占比假设为 45%"],
    }
    changes = json.loads(patched.stdout)["normalization_changes"]
    assert "truth_contract.mode: ignored patch mutation and preserved scaffold mode" in changes
    assert (
        "truth_contract.source_facts: ignored patch mutation and preserved scaffold facts"
        in changes
    )


def test_truth_validator_rechecks_strict_source_fact_provenance(tmp_path: Path) -> None:
    source_text = "NOON Studio，2026 年是第三年。只使用我提供的事实，禁止虚构。"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--fact",
        "NOON Studio",
        "--fact",
        "2026 年是第三年",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text())
    deck["truth_contract"]["source_facts"].append("成立于 2024 年")
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path), env=env)

    assert result.returncode == 1
    payload = json.loads(result.stdout.split("\nDeck truth validation:", 1)[0])
    assert payload["sourceBinding"]["strict"] is True
    assert any("成立于 2024 年" in issue for issue in payload["issues"])


def test_strict_truth_validator_rejects_invented_narrative_and_unlabeled_concept_media(
    tmp_path: Path,
) -> None:
    source_text = (
        "NOON Studio。2026 年是第三年。品牌视觉 + 数字产品设计。"
        "今年交付 28 个项目。覆盖 SaaS、消费品、文化机构三个领域。"
        "页面包括合作客户、获奖与刊载、团队、流程、明年。"
        "只使用我提供的事实，禁止虚构。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "statement-focus-v1",
        "kpi-grid-v1",
        "project-case-study-v1",
        "timeline-horizontal-v1",
        "cards-grid-v1",
        "--fact",
        "NOON Studio",
        "--fact",
        "2026 年是第三年",
        "--fact",
        "品牌视觉 + 数字产品设计",
        "--fact",
        "今年交付 28 个项目",
        "--fact",
        "SaaS、消费品、文化机构三个领域",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "statement": "成为更有影响力的设计工作室",
            "support": "持续拓展国际客户与长期品牌价值",
            "proofs": [{"value": "获奖数量翻倍", "label": "明年目标"}],
        }
    )
    deck["slides"][1]["props"]["items"] = [
        {"label": "PROJECTS", "value": "28", "detail": "全年高质量交付", "delta": ""},
        {"label": "CLIENTS", "value": "待补充", "detail": "待补充", "delta": ""},
        {"label": "AWARDS", "value": "待补充", "detail": "待补充", "delta": ""},
    ]
    deck["slides"][2]["props"].update(
        {
            "title": "品牌项目 A（待补充）",
            "positioning": "从 0 到 1 构建 SaaS 品牌识别系统",
            "image": {
                "src": "assets/generated/project-brand.png",
                "alt": "SaaS 品牌项目实景",
            },
            "metrics": [
                {"value": "待补充", "label": "项目指标"},
                {"value": "待补充", "label": "项目结果"},
            ],
            "caption": "项目上线后获得客户一致认可",
        }
    )
    deck["slides"][3]["props"]["steps"] = [
        {"phase": "阶段 1", "title": "深度理解", "body": "与客户共创业务洞察"},
        {"phase": "阶段 2", "title": "大胆提案", "body": "用视觉建立差异化"},
        {"phase": "阶段 3", "title": "快速迭代", "body": "持续验证并完善方案"},
    ]
    deck["slides"][4]["props"].update(
        {
            "title": "团队",
            "items": [
                {"kicker": "01", "title": "设计", "body": "负责品牌与产品体验"},
                {"kicker": "02", "title": "策略", "body": "连接商业与创意"},
                {"kicker": "03", "title": "技术", "body": "推动数字产品落地"},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path), env=env)

    assert result.returncode == 1
    payload = json.loads(result.stdout.split("\nDeck truth validation:", 1)[0])
    issues = "\n".join(payload["issues"])
    assert "strict source-only field is not source-backed" in issues
    assert "generated project media must declare origin" in issues
    assert "generated project media must be labeled as AI concept/placeholder" in issues
    assert "slides.slide-04.props.steps.0.title" in issues
    assert "team-member name is not source-backed" in issues


def test_strict_truth_validator_accepts_exact_copy_placeholders_and_labeled_concept_media(
    tmp_path: Path,
) -> None:
    source_text = (
        "NOON Studio。2026 年是第三年。品牌视觉 + 数字产品设计。"
        "今年交付 28 个项目。流程是理解、提案、迭代。"
        "只使用我提供的事实，禁止虚构。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "statement-focus-v1",
        "kpi-grid-v1",
        "project-case-study-v1",
        "timeline-horizontal-v1",
        "cards-grid-v1",
        "--fact",
        "NOON Studio",
        "--fact",
        "2026 年是第三年",
        "--fact",
        "品牌视觉 + 数字产品设计",
        "--fact",
        "今年交付 28 个项目",
        "--fact",
        "流程是理解、提案、迭代",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "statement": "2026 年是第三年",
            "support": "品牌视觉 + 数字产品设计",
            "proofs": [{"value": "今年交付 28 个项目", "label": "项目"}],
        }
    )
    deck["slides"][1]["props"]["items"] = [
        {"label": "PROJECTS", "value": "28", "detail": "今年交付 28 个项目", "delta": ""},
        {"label": "CLIENTS", "value": "待补充", "detail": "待补充", "delta": ""},
        {"label": "AWARDS", "value": "待补充", "detail": "待补充", "delta": ""},
    ]
    deck["slides"][2]["props"].update(
        {
            "title": "品牌项目 A（待补充）",
            "positioning": "品牌视觉 + 数字产品设计",
            "image": {
                "src": "assets/generated/project-brand.png",
                "alt": "AI 概念视觉，实际项目图待补充",
                "origin": "generated",
            },
            "metrics": [
                {"value": "待补充", "label": "项目指标"},
                {"value": "待补充", "label": "项目结果"},
            ],
            "caption": "AI 概念视觉，实际项目图待补充",
        }
    )
    deck["slides"][3]["props"]["steps"] = [
        {"phase": "阶段 1", "title": "理解", "body": "待补充"},
        {"phase": "阶段 2", "title": "提案", "body": "待补充"},
        {"phase": "阶段 3", "title": "迭代", "body": "待补充"},
    ]
    deck["slides"][4]["props"].update(
        {
            "title": "团队",
            "items": [
                {"kicker": "01", "title": "团队成员待补充", "body": "待补充"},
                {"kicker": "02", "title": "团队成员待补充", "body": "待补充"},
                {"kicker": "03", "title": "团队成员待补充", "body": "待补充"},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path), env=env)

    assert result.returncode == 0, result.stdout + result.stderr


def test_controlled_batch_patch_preserves_layout_contract_and_scaffolded_facts(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "statement-focus-v1",
        "--fact",
        "NOON Studio",
        "--fact",
        "2026 年是第三年",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "truth_contract": {
                    "mode": "source_bound",
                    "source_facts": ["NOON Studio", "2026 年是第三年", "今年交付 28 个项目"],
                },
                "slides": {
                    "slide-01": {
                        "props": {
                            "headline": "NOON Studio",
                            "subhead": "2026 · 第三年",
                            "kicker": "品牌视觉 + 数字产品设计",
                            "caption": "今年交付 28 个项目",
                            "image": {
                                "path": "assets/generated/cover-hero.png",
                                "alt_text": "NOON Studio 封面视觉",
                            },
                        }
                    },
                    "slide-02": {
                        "props": {
                            "statement": "第三年，继续把设计做深。",
                            "support": "品牌视觉 × 数字产品设计",
                        }
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stderr
    deck = json.loads(deck_path.read_text())
    assert [slide["layout_id"] for slide in deck["slides"]] == [
        "cover-hero-v1",
        "statement-focus-v1",
    ]
    assert deck["slides"][0]["props"]["title"] == "NOON Studio"
    assert deck["slides"][0]["props"]["subtitle"] == "2026 · 第三年"
    assert deck["slides"][0]["props"]["eyebrow"] == "品牌视觉 + 数字产品设计"
    assert deck["slides"][0]["props"]["meta"] == "今年交付 28 个项目"
    assert deck["slides"][0]["props"]["hero"] == {
        "src": "assets/generated/cover-hero.png",
        "alt": "NOON Studio 封面视觉",
        "origin": "generated",
    }
    assert deck["truth_contract"]["source_facts"] == [
        "NOON Studio",
        "2026 年是第三年",
    ]
    payload = json.loads(result.stdout)
    assert (
        "truth_contract.source_facts: ignored patch mutation and preserved scaffold facts"
        in payload["normalization_changes"]
    )


def test_batch_patch_normalizes_nested_architecture_module_capacity(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "architecture-layered-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "layers": [
                                {
                                    "label": "TOUCHPOINT",
                                    "title": "用户触点层",
                                    "modules": ["官网", "APP"],
                                },
                                {
                                    "label": "AI SERVICE",
                                    "title": "智能服务层",
                                    "modules": [
                                        "意图识别",
                                        "多轮对话",
                                        "知识检索",
                                        "会话路由",
                                        "人工转接",
                                        "额外模块",
                                    ],
                                },
                                {
                                    "label": "INTEGRATION",
                                    "title": "业务集成层",
                                    "modules": ["订单系统", "会员系统"],
                                },
                            ]
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    modules = deck["slides"][0]["props"]["layers"][1]["modules"]
    assert modules == ["意图识别", "多轮对话", "知识检索", "会话路由", "人工转接"]
    payload = json.loads(result.stdout)
    assert (
        "slides.slide-01.props.layers.1.modules: truncated to 5 items"
        in payload["normalization_changes"]
    )


def test_batch_patch_moves_need_solution_value_source_to_table_insight(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "table-data-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    source = (
        "需求：客户需要清楚评估实施阶段、责任分工、关键里程碑、验收边界和上线风险。"
        "方案：按启动、调研、建设、集成、测试、试点、推广和优化分阶段推进。"
        "价值：通过试点验证和分阶段推广控制风险，让业务与技术团队逐步进入稳定运营。"
    )
    assert len(source) > 100
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {"slides": {"slide-01": {"props": {"source": source}}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["props"]["source"] == ""
    assert deck["slides"][0]["props"]["insight"] == (
        "客户收益：通过试点验证和分阶段推广控制风险，让业务与技术团队逐步进入稳定运营。"
    )
    payload = json.loads(result.stdout)
    assert (
        "slides.slide-01.props.source: moved overlong need-solution-value copy to insight"
        in payload["normalization_changes"]
    )
    html_path = tmp_path / "index.html"
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    assert rendered.returncode == 0, rendered.stderr
    html = html_path.read_text(encoding="utf-8")
    assert 'class="table-insight" data-prop-path="insight"' in html
    assert "客户收益：通过试点验证和分阶段推广控制风险" in html


def test_batch_patch_compacts_overlong_optional_source_caption(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "table-data-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    source = "来源：客户提供的项目资料与内部访谈纪要；" + "补充来源说明" * 20
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {"slides": {"slide-01": {"props": {"source": source}}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stdout + result.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    compacted = deck["slides"][0]["props"]["source"]
    assert 0 < len(compacted) <= 100
    assert compacted.startswith("来源：客户提供的项目资料与内部访谈纪要")
    payload = json.loads(result.stdout)
    assert (
        "slides.slide-01.props.source: compacted optional source caption to 100 characters"
        in payload["normalization_changes"]
    )


def test_batch_patch_wraps_unambiguous_top_level_slide_ids(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "statement-focus-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slide-01": {"props": {"title": "巴西足球历史"}},
                "slide-02": {"props": {"statement": "五冠之外，风格仍在延续"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["patched_slides"] == ["slide-01", "slide-02"]
    assert (
        'patch: nested direct slide-id keys under the top-level "slides" object'
        in payload["normalization_changes"]
    )
    deck = json.loads(deck_path.read_text())
    assert deck["slides"][0]["props"]["title"] == "巴西足球历史"
    assert deck["slides"][1]["props"]["statement"] == "五冠之外，风格仍在延续"


def test_batch_patch_removes_only_redundant_trailing_json_closers(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    valid_patch = {
        "slides": {"slide-01": {"props": {"title": "安全恢复后的标题"}}}
    }
    patch_path.write_text(
        json.dumps(valid_patch, ensure_ascii=False) + "}\n",
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "patch: removed 1 redundant trailing JSON closer(s)" in payload[
        "normalization_changes"
    ]
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert deck["slides"][0]["props"]["title"] == "安全恢复后的标题"

    invalid_patch = tmp_path / "invalid.patch.json"
    invalid_patch.write_text(
        '{"slides":{"slide-01":{"props":{"title":}}}}',
        encoding="utf-8",
    )
    rejected = _run("apply_deck_patch.js", str(deck_path), str(invalid_patch))
    assert rejected.returncode == 1
    assert "Invalid JSON" in rejected.stderr


def test_batch_patch_normalizes_background_type_and_missing_kpi_detail(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "kpi-grid-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "background": {
                            "type": "image",
                            "src": "assets/generated/slide-01-hero.png",
                        }
                    },
                    "slide-02": {
                        "props": {
                            "items": [
                                {"label": "成立年数", "value": "3", "unit": "年"},
                                {"label": "交付项目", "value": "28", "unit": "个"},
                                {"label": "覆盖领域", "value": "3", "unit": "个"},
                                {
                                    "label": "业务方向",
                                    "value": "品牌视觉 + 数字产品设计",
                                },
                            ]
                        }
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert "slides.slide-01.background.type: dropped unknown media field" in payload[
        "normalization_changes"
    ]
    deck = json.loads(deck_path.read_text())
    assert deck["slides"][0]["background"] == {
        "src": "assets/generated/slide-01-hero.png",
        "alt": "AI 生成的背景概念视觉",
        "origin": "generated",
        "fit": "cover",
        "position": "center",
        "treatment": "wash-light",
    }
    items = deck["slides"][1]["props"]["items"]
    assert [item["value"] for item in items] == [
        "3年",
        "28个",
        "3个",
        "品牌视觉 + 数字产品设计",
    ]
    assert all(item.get("detail", "") == "" for item in items)


def test_batch_patch_normalizes_background_image_and_string_proofs(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "statement-focus-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "background": {
                            "image": "assets/generated/slide-01-cover.png",
                            "origin": "generated",
                            "alt": "NOON Studio 2026 封面",
                        }
                    },
                    "slide-02": {
                        "props": {
                            "proofs": [
                                "28 个项目",
                                "SaaS / 消费品 / 文化机构",
                                "第三年",
                            ],
                            "proof_style": "block",
                            "emphasis": "statement",
                        }
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("apply_deck_patch.js", str(deck_path), str(patch_path))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    changes = payload["normalization_changes"]
    assert "slides.slide-01.background.image: mapped to src" in changes
    assert "slides.slide-02.props.proofs.0: converted proof text to an object" in changes
    deck = json.loads(deck_path.read_text())
    assert deck["slides"][0]["background"]["src"] == (
        "assets/generated/slide-01-cover.png"
    )
    assert deck["slides"][0]["background"]["alt"] == "NOON Studio 2026 封面"
    assert deck["slides"][1]["props"]["proofs"] == [
        {"value": "28 个项目", "label": ""},
        {"value": "SaaS / 消费品 / 文化机构", "label": ""},
        {"value": "第三年", "label": ""},
    ]
    assert deck["slides"][1]["props"]["proof_style"] == "auto"
    assert deck["slides"][1]["props"]["emphasis"] == "balanced"

    html_path = tmp_path / "index.html"
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    html = html_path.read_text(encoding="utf-8")
    assert 'class="proof-label"' not in html
    assert ">待补充<" not in html


def test_strict_batch_patch_normalizes_observed_model_drift_in_one_pass(
    tmp_path: Path,
) -> None:
    source_text = (
        "做一份 NOON Studio 作品集。2026 年是第三年，"
        "业务是品牌视觉 + 数字产品设计，今年交付 28 个项目，"
        "覆盖 SaaS、消费品、文化机构三个领域。"
        "页面包括合作客户、获奖与刊载、团队、流程、明年。"
        "只使用我提供的事实，禁止虚构。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    original_facts = [
        "NOON Studio",
        "2026 年是第三年",
        "业务是品牌视觉 + 数字产品设计",
        "今年交付 28 个项目",
        "覆盖 SaaS、消费品、文化机构三个领域",
    ]
    scaffold_args: list[str] = [
        "cover-hero-v1",
        "statement-focus-v1",
        "kpi-grid-v1",
        "project-case-study-v1",
        "cards-grid-v1",
        "timeline-horizontal-v1",
    ]
    for fact in original_facts:
        scaffold_args.extend(["--fact", fact])
    scaffold_args.extend(["--out", str(deck_path)])
    scaffold = _run("inspect_deck_contract.js", *scaffold_args, env=env)
    assert scaffold.returncode == 0, scaffold.stderr

    patch_path = tmp_path / "deck.patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "truth_contract": {
                    "mode": "source_bound",
                    "source_facts": [
                        "NOON Studio 成立于 2024 年，2026 年是第三年",
                        "2026 年交付 28 个项目",
                    ],
                },
                "slides": {
                    "slide-01": {
                        "props": {
                            "title": "NOON Studio",
                            "subtitle": "品牌视觉 × 数字产品设计",
                            "caption": "2024-2026",
                            "hero": "assets/generated/slide-01-cover.png",
                        }
                    },
                    "slide-02": {
                        "props": {
                            "statement": "第三年，28 个项目，三个领域，一条主线",
                            "subtitle": "成立于 2024 年，持续拓展国际客户",
                            "proofs": [
                                {"label": "成立年份", "value": "2024"},
                            ],
                        }
                    },
                    "slide-03": {
                        "props": {
                            "items": [
                                {
                                    "label": "交付项目",
                                    "value": "28",
                                    "unit": "个",
                                    "trend": "2026 全年",
                                },
                                {
                                    "label": "覆盖领域",
                                    "value": "3",
                                    "trend": "SaaS · 消费品 · 文化机构",
                                },
                                {
                                    "label": "运营年限",
                                    "value": "3rd",
                                    "trend": "2026 年是工作室第三年",
                                },
                                {
                                    "label": "业务方向",
                                    "value": "2",
                                    "trend": "品牌视觉 · 数字产品设计",
                                },
                            ]
                        }
                    },
                    "slide-04": {
                        "props": {
                            "title": "品牌项目 A",
                            "client": "某知名客户",
                            "year": "2026",
                            "tags": ["品牌视觉"],
                            "summary": "从 0 到 1 构建品牌识别系统",
                            "image": {
                                "path": "assets/generated/slide-04-brand.png",
                                "alt_text": "品牌项目实景",
                            },
                            "metrics": [
                                {"label": "项目指标", "value": "待补充"},
                                {"label": "结果指标", "value": "待补充"},
                            ],
                            "composition": "image-right",
                        }
                    },
                    "slide-05": {
                        "props": {
                            "eyebrow": "合作客户",
                            "title": "他们选择了 NOON",
                            "subtitle": "被不同领域持续信任",
                            "items": [
                                {"title": "客户 A", "description": "长期合作"},
                                {"title": "SaaS 领域", "description": "待补充"},
                                {"title": "客户 C", "description": "待补充"},
                            ],
                        }
                    },
                    "slide-06": {
                        "props": {
                            "title": "我们的流程",
                            "subtitle": "每个项目都经历三个阶段，确保从理解到交付的一致性",
                            "steps": [
                                {"phase": "01", "title": "发现", "description": "理解客户"},
                                {"phase": "02", "title": "设计", "description": "大胆提案"},
                                {"phase": "03", "title": "交付", "description": "确保落地"},
                            ],
                        }
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["normalization_changes"]
    assert payload["truth_guard_changes"]
    deck = json.loads(deck_path.read_text())
    assert deck["truth_contract"]["source_facts"] == original_facts
    serialized = json.dumps(deck, ensure_ascii=False)
    assert "2024" not in serialized
    assert "某知名客户" not in serialized
    assert "client" not in deck["slides"][3]["props"]
    assert "summary" not in deck["slides"][3]["props"]
    assert deck["slides"][3]["props"]["positioning"] == "待补充"
    assert deck["slides"][3]["props"]["image"]["origin"] == "generated"
    assert "AI 概念" in deck["slides"][3]["props"]["image"]["alt"]
    assert "path" not in deck["slides"][3]["props"]["image"]
    assert "alt_text" not in deck["slides"][3]["props"]["image"]
    assert deck["slides"][4]["props"]["title"] == "合作客户"
    assert deck["slides"][4]["props"]["subtitle"] == "待补充"
    assert deck["slides"][4]["props"]["items"][0]["body"] == "待补充"
    assert deck["slides"][5]["props"]["title"] == "我们的流程"
    assert deck["slides"][5]["props"]["subtitle"] == ""
    assert deck["slides"][5]["props"]["steps"][0]["title"] == "待补充"
    assert deck["slides"][2]["props"]["items"][1]["value"] == "3"
    assert deck["slides"][2]["props"]["items"][3]["value"] == "待补充"

    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr

    deck["slides"][4]["props"]["title"] = "他们选择了 NOON"
    deck["slides"][4]["props"]["subtitle"] = "被不同领域持续信任"
    deck["slides"][5]["props"]["title"] = "这套流程确保每个项目成功"
    deck["slides"][5]["props"]["subtitle"] = "每个项目都经历三个阶段"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    rejected_truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert rejected_truth.returncode == 1
    rejected_payload = json.loads(
        rejected_truth.stdout.split("\nDeck truth validation:", 1)[0]
    )
    rejected_issues = "\n".join(rejected_payload["issues"])
    assert "slides.slide-05.props.title" in rejected_issues
    assert "slides.slide-05.props.subtitle" in rejected_issues
    assert "slides.slide-06.props.title" in rejected_issues
    assert "slides.slide-06.props.subtitle" in rejected_issues


def test_truth_validator_rejects_observed_unsourced_claims(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "statement-focus-v1",
        "--fact",
        "NOON Studio",
        "--fact",
        "2026 年是第三年",
        "--fact",
        "今年交付 28 个项目",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "title": "NOON Studio",
            "meta": "EST. 2024",
        }
    )
    deck["slides"][1]["props"]["proofs"] = [
        {"label": "客户关系", "value": "客户复购率持续提升"},
        {"label": "团队发展", "value": "团队从 3 人走到今天"},
    ]
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 1
    payload = json.loads(result.stdout.split("\nDeck truth validation:", 1)[0])
    issues = "\n".join(payload["issues"])
    assert 'numeric claim "2024"' in issues
    assert "performance/award/publication claim is not source-backed" in issues
    assert "team-size claim is not source-backed" in issues


def test_truth_validator_allows_qualitative_problem_and_expected_value_copy(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "--fact",
        "AA 科技能力包括 AI 客服机器人、知识库管理、人工转接和数据看板",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "需求 — 方案 — 价值",
            "title": "客户价值",
            "subtitle": (
                "需求：客户希望降低人工客服压力并提升响应速度。"
                "方案：以 AI 客服机器人连接知识库、人工转接和数据看板。"
                "价值：让采购、IT、业务同时看到成本可控、技术可信、运营可持续。"
            ),
            "items": [
                {
                    "kicker": "01",
                    "title": "客户痛点",
                    "body": (
                        "复杂咨询转人工时若上下文丢失，客户需要重复描述问题，"
                        "人工处理效率也会下降。"
                    ),
                },
                {
                    "kicker": "02",
                    "title": "预期收益",
                    "body": (
                        "客户在控制人工资源投入的同时，"
                        "提升复杂问题处理效率和服务连续性。"
                    ),
                },
                {
                    "kicker": "03",
                    "title": "风险控制",
                    "body": (
                        "客户可在稳妥前提下推进智能客服升级，"
                        "降低技术、业务和运营风险。"
                    ),
                },
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_truth_validator_accepts_user_backed_case_coverage_paraphrase(
    tmp_path: Path,
) -> None:
    source_fact = "已有案例覆盖：电商、零售、教育。"
    source_text = (
        "请生成客户评标 PPT。"
        f"{source_fact}"
        "案例页的真实客户名称和关键数字未提供时使用待补充占位。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    patch_path = tmp_path / "deck.patch.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "table-data-v1",
        "--fact",
        source_fact,
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    patch_path.write_text(
        json.dumps(
            {
                "slides": {
                    "slide-01": {
                        "props": {
                            "eyebrow": "行业案例",
                            "title": "电商、零售、教育行业案例",
                            "subtitle": (
                                "AA 科技已有电商、零售和教育行业覆盖场景材料，"
                                "可为本项目沉淀可复用的实施方法；"
                                "具体客户名称与量化成果待授权补充。"
                            ),
                            "columns": ["行业案例", "成果说明", "关键数字"],
                            "rows": [
                                ["电商", "场景说明待补充", "待补充"],
                                ["零售", "场景说明待补充", "待补充"],
                                ["教育", "场景说明待补充", "待补充"],
                            ],
                            "source": source_fact,
                            "variant": "ledger",
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    applied = _run(
        "apply_deck_patch.js",
        str(deck_path),
        str(patch_path),
        env=env,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    assert "覆盖场景材料" in deck["slides"][0]["props"]["subtitle"]
    truth = _run("validate_deck_truth.js", str(deck_path), env=env)
    assert truth.returncode == 0, truth.stdout + truth.stderr


def test_truth_validator_rejects_extra_observed_result_in_coverage_paraphrase(
    tmp_path: Path,
) -> None:
    source_fact = "已有案例覆盖：电商、零售、教育。"
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "table-data-v1",
        "--fact",
        source_fact,
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"]["subtitle"] = (
        "AA 科技已有电商、零售和教育行业覆盖，并已实现客户成本降低。"
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 1
    issues = json.loads(
        result.stdout.split("\nDeck truth validation:", 1)[0]
    )["issues"]
    assert any("performance/award/publication claim" in issue for issue in issues)


def test_truth_validator_accepts_dotted_date_and_transition_wording(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-editorial-v1",
        "kpi-grid-v1",
        "--research-fact",
        "拉明·亚马尔出生于2007年7月13日。",
        "--research-fact",
        "2024/25赛季55次出场、18球、21助攻。",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "title": "拉明·亚马尔",
            "subtitle": "出生于2007年7月13日",
            "marker": "2007.7.13",
        }
    )
    deck["slides"][1]["props"].update(
        {
            "title": "成长与俱乐部表现",
            "subtitle": "早熟纪录已经转化为巴萨可见产出。",
            "items": [
                {
                    "label": "赛季出场",
                    "value": "55",
                    "detail": "2024/25赛季55次出场、18球、21助攻。",
                    "delta": "",
                },
                {
                    "label": "赛季进球",
                    "value": "18",
                    "detail": "2024/25赛季55次出场、18球、21助攻。",
                    "delta": "",
                },
                {
                    "label": "赛季助攻",
                    "value": "21",
                    "detail": "2024/25赛季55次出场、18球、21助攻。",
                    "delta": "",
                },
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_truth_validator_accepts_pitch_assumptions_and_capability_sections(
    tmp_path: Path,
) -> None:
    source_text = (
        "产品为面向中小制造工厂的 AI 质检 + 智能排产平台。"
        "已有 30 家试点客户。当前年化收入 800 万元。"
        "未提供的增长曲线和竞争评分可以使用合理假设数据，"
        "但必须标明示意 / 假设。团队姓名未提供，不要虚构个人信息。"
    )
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "table-data-v1",
        "chart-data-v1",
        "cards-grid-v1",
        "--fact",
        "产品为面向中小制造工厂的 AI 质检 + 智能排产平台",
        "--fact",
        "已有 30 家试点客户",
        "--fact",
        "当前年化收入 800 万元",
        "--assumption",
        "示意 / 假设：增长曲线使用 100、400、800 万元和 10、20、30 家；竞争评分仅用于表达产品定位。",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr

    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "商业模式｜先切刚需，再扩平台",
            "title": "订阅、模型与交付服务形成组合收入",
            "subtitle": "客户按产线与模块付费，具体合同数据待补充。",
            "items": [
                {"kicker": "订阅", "title": "软件订阅", "body": "按年使用平台。"},
                {"kicker": "模型", "title": "模型包", "body": "按场景配置。"},
                {"kicker": "服务", "title": "交付服务", "body": "按项目实施。"},
            ],
        }
    )
    deck["slides"][1]["props"].update(
        {
            "eyebrow": "竞争格局｜示意 / 假设",
            "title": "竞争维度对比",
            "subtitle": "示意 / 假设：评分只表达产品定位，不代表公开排名。",
            "columns": ["维度", "本项目", "传统软件"],
            "rows": [["AI 质检", "强", "弱"], ["智能排产", "强", "中"]],
            "source": "示意 / 假设：待真实竞品调研校准。",
        }
    )
    deck["slides"][2]["props"].update(
        {
            "eyebrow": "业务进展",
            "title": "试点客户与年化收入",
            "subtitle": "增长曲线为示意 / 假设；当前锚点来自用户事实。",
            "chart_type": "line",
            "categories": ["早期", "中期", "当前"],
            "series": [
                {"name": "年化收入（万元，假设）", "values": ["100", "400", "800"]},
                {"name": "试点客户数（家，假设）", "values": ["10", "20", "30"]},
            ],
            "insight": "示意 / 假设：增长路径用于路演表达。",
            "source": "事实：已有 30 家试点客户；当前年化收入 800 万元。",
        }
    )
    deck["slides"][3]["props"].update(
        {
            "eyebrow": "团队｜复合能力结构",
            "title": "团队",
            "subtitle": "团队姓名与履历未提供，以下只表达能力结构，不虚构个人信息。",
            "items": [
                {"kicker": "AI", "title": "算法与工程化", "body": "能力方向：视觉识别与稳定部署。"},
                {"kicker": "制造", "title": "工艺与现场理解", "body": "能力方向：产线与排产工作流。"},
                {"kicker": "SaaS", "title": "企业服务产品化", "body": "能力方向：平台模块化。"},
                {"kicker": "GTM", "title": "销售与交付体系", "body": "能力方向：试点与交付。"},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path), env=env)

    assert result.returncode == 0, result.stdout + result.stderr


def test_truth_validator_accepts_source_facts_and_honest_placeholders(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "statement-focus-v1",
        "kpi-grid-v1",
        "project-case-study-v1",
        "--fact",
        "NOON Studio",
        "--fact",
        "2026 年是第三年",
        "--fact",
        "今年交付 28 个项目",
        "--fact",
        "业务是品牌视觉 + 数字产品设计",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "NOON Studio",
            "title": "2026 YEAR IN REVIEW",
            "subtitle": "第三年",
            "meta": "28 PROJECTS",
        }
    )
    deck["slides"][1]["props"].update(
        {
            "statement": "第三年，继续把设计做深。",
            "support": "品牌视觉 × 数字产品设计",
            "proofs": [],
        }
    )
    deck["slides"][2]["props"]["items"] = [
        {"label": "PROJECTS", "value": "28", "detail": "全年交付", "delta": ""},
        {"label": "CLIENTS", "value": "待补充", "detail": "客户数", "delta": ""},
        {"label": "AWARDS", "value": "待补充", "detail": "获奖数", "delta": ""},
        {"label": "TEAM", "value": "待补充", "detail": "团队人数", "delta": ""},
    ]
    deck["slides"][3]["props"].update(
        {
            "title": "品牌项目 A（待补充）",
            "positioning": "品牌视觉与数字产品的协同设计。",
            "metrics": [
                {"value": "待补充", "label": "项目指标"},
                {"value": "待补充", "label": "项目结果"},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    report = tmp_path / "qa" / "truth_check.json"

    result = _run(
        "validate_deck_truth.js",
        str(deck_path),
        "--report",
        str(report),
    )

    assert result.returncode == 0, result.stdout
    assert json.loads(report.read_text())["ok"] is True


def test_truth_validator_allows_non_project_story_in_case_study_visual_layout(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "project-case-study-v1",
        "--research-fact",
        "FIFA 公开资料记录巴西在 1958、1962、1970 年获得世界杯冠军。",
        "--research-fact",
        "贝利是巴西黄金时代的代表人物。",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr

    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "黄金时代",
            "title": "黄金时代：贝利与三次世界杯冠军",
            "positioning": "1958、1962、1970 三次夺冠将巴西足球推向黄金时代。",
            "metrics": [
                {"value": "1958", "label": "首次登顶"},
                {"value": "1962", "label": "成功卫冕"},
                {"value": "1970", "label": "黄金高峰"},
            ],
            "caption": "贝利是巴西黄金时代的代表人物。",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_truth_validator_still_rejects_unbacked_real_project_name(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "project-case-study-v1",
        "--fact",
        "NOON Studio",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr

    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "项目案例",
            "title": "品牌项目 Alpha",
            "positioning": "NOON Studio",
            "metrics": [
                {"value": "待补充", "label": "业务结果"},
                {"value": "待补充", "label": "设计影响"},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 1
    payload = json.loads(result.stdout.split("\nDeck truth validation:", 1)[0])
    assert any("project name is not source-backed" in issue for issue in payload["issues"])


def test_truth_validator_accepts_chinese_quantity_and_section_marker_number(
    tmp_path: Path,
) -> None:
    source_text = "制作一个关于巴西足球历史的 PPT"
    env = os.environ.copy()
    env["BOX_AGENT_SOURCE_TEXT_B64"] = base64.b64encode(
        source_text.encode("utf-8")
    ).decode("ascii")
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "kpi-grid-v1",
        "section-marker-v1",
        "--research-fact",
        "巴西男足国家队五次获得 FIFA World Cup 冠军。",
        "--out",
        str(deck_path),
        env=env,
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr

    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "title": "世界杯冠军",
            "items": [
                {
                    "label": "冠军次数",
                    "value": "5",
                    "detail": "巴西男足国家队五次获得 FIFA World Cup 冠军。",
                    "delta": "",
                },
                {
                    "label": "待补充",
                    "value": "待补充",
                    "detail": "待补充",
                    "delta": "",
                },
                {
                    "label": "待补充",
                    "value": "待补充",
                    "detail": "待补充",
                    "delta": "",
                },
            ],
        }
    )
    deck["slides"][1]["props"].update(
        {
            "number": "06",
            "eyebrow": "SECTION",
            "title": "巴西足球历史",
            "subtitle": "",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path), env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.split("\nDeck truth validation:", 1)[0])
    assert payload["ok"] is True


def test_truth_validator_accepts_cover_slide_count_metadata(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "statement-focus-v1",
        "--fact",
        "历史梳理",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr

    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"]["meta"] = "2 页历史梳理 · HTML 交付"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_truth.js", str(deck_path))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.split("\nDeck truth validation:", 1)[0])
    assert payload["ok"] is True


def test_controlled_deck_scripts_resolve_relative_paths_from_canonical_output_root(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "session" / "output"
    wrong_cwd = tmp_path / "session"
    canonical.mkdir(parents=True)
    env = os.environ.copy()
    env["BOX_AGENT_OUTPUT_DIR"] = str(canonical)

    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-hero-v1",
        "statement-focus-v1",
        "--theme",
        "block-frame",
        "--title",
        "Canonical root",
        "--out",
        "deck.json",
        cwd=wrong_cwd,
        env=env,
    )

    assert scaffold.returncode == 0, scaffold.stderr
    assert (canonical / "deck.json").is_file()
    assert (canonical / "assets/generated/manifest.json").is_file()
    assert (canonical / "qa/deck_contract.json").is_file()
    assert not (wrong_cwd / "deck.json").exists()

    validation = _run(
        "validate_deck_spec.js",
        "deck.json",
        "--report",
        "qa/deck_spec.json",
        cwd=wrong_cwd,
        env=env,
    )
    rendered = _run(
        "render_deck_html.js",
        "deck.json",
        "--out",
        "index.html",
        cwd=wrong_cwd,
        env=env,
    )

    assert validation.returncode == 0, validation.stderr
    assert rendered.returncode == 0, rendered.stderr
    assert json.loads((canonical / "qa/deck_spec.json").read_text())["ok"] is True
    assert (canonical / "index.html").is_file()
    assert not (wrong_cwd / "index.html").exists()


def test_pptx_theme_selection_has_no_hard_html_templates_dependency() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---", 2)[1])

    assert "html-templates" not in (frontmatter.get("required_skills") or [])
    assert "html-templates" in frontmatter["related_skills"]
    assert "Source-bound decks never invent named clients" in text
    assert "复购率持续提升" in text
    assert "Never create a fake bitmap with Pillow" in text
    assert "--out deck.json" in text
    assert "--require-field" in text
    assert "BOX_AGENT_OUTPUT_DIR" in text
    assert 'write_file(path="deck.json", ...)' in text
    assert "required `image_plan` key" in text
    assert "apply_deck_patch.js" in text
    assert "${BOX_AGENT_NODE:-node} scripts/apply_deck_patch.js" in text
    assert "validate_deck_truth.js" in text


def test_pptx_missing_required_input_resumes_existing_deck() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "call `request_user_input` once with one focused question" in text
    assert "The user's next reply resumes this same deck" in text
    assert "do not scaffold a second `deck.json`" in text


def test_outline_validator_writes_report_and_flags_reused_evidence(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    report_path = tmp_path / "qa" / "outline_check.json"
    shared_evidence = (
        "巴西男足国家队五次获得 FIFA World Cup 冠军。 | FIFA | "
        "https://www.fifa.com/example"
    )
    outline_path.write_text(
        json.dumps(
            {
                "deck_goal": "解释巴西足球历史的关键阶段",
                "audience": "普通体育观众",
                "source_mode": "public_authoritative_research",
                "storyline": "从组织起点到冠军时代，再总结其全球影响。",
                "slides": [
                    {
                        "page": index,
                        "title": f"阶段 {label}",
                        "message": f"第{label}页承担不同的历史叙事任务",
                        "bullets": ["事实线索一", "事实线索二"],
                        "layout": "timeline",
                        "visual": "时间线",
                        "evidence": [shared_evidence],
                        "notes": "",
                    }
                    for index, label in enumerate(("一", "二", "三"), start=1)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run(
        "validate_outline.js",
        str(outline_path),
        "--report",
        str(report_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert any("evidence is reused across 3 slides" in item for item in report["warnings"])


def test_outline_array_audience_and_storyline_pass_validation_and_scaffold(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=3,
        source_mode="user_provided",
    )
    outline["audience"] = ["采购负责人", "IT 负责人", "业务负责人"]
    outline["storyline"] = [
        "先说明客户需求与评审重点。",
        "再展开解决方案、系统集成与实施计划。",
        "最后以客户价值和下一步收束。",
    ]
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )

    validation = _run(
        "validate_outline.js",
        str(outline_path),
        "--report",
        str(tmp_path / "qa" / "outline_check.json"),
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr
    assert json.loads(validation.stdout)["ok"] is True

    scaffold = _run(
        "inspect_deck_contract.js",
        "cards-grid-v1",
        "cards-grid-v1",
        "closing-next-steps-v1",
        "--theme",
        "auto",
        "--outline",
        str(outline_path),
        "--out",
        str(tmp_path / "deck.json"),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    assert (tmp_path / "deck.json").is_file()
    assert (tmp_path / "assets" / "generated" / "manifest.json").is_file()


def test_public_research_outline_requires_numeric_claims_in_page_evidence(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline_path.write_text(
        json.dumps(
            {
                "deck_goal": "解释巴西足球历史的关键阶段",
                "audience": "普通体育观众",
                "source_mode": "public_authoritative_research",
                "storyline": "从早期参赛到首次夺冠。",
                "slides": [
                    {
                        "page": 1,
                        "title": "1930 年开启国际参赛史",
                        "message": "巴西持续积累国际大赛经验。",
                        "bullets": ["逐步形成技术风格", "最终进入冠军行列"],
                        "layout": "timeline",
                        "visual": "时间线",
                        "evidence": [
                            "公开资料确认 1958 年首次夺冠。 | FIFA | "
                            "https://www.fifa.com/example"
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run(
        "validate_outline.js",
        str(outline_path),
        "--min-slides",
        "1",
        "--max-slides",
        "1",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        'title numeric literal "1930" is not present in this page\'s evidence'
        in issue
        for issue in payload["issues"]
    )


def test_public_research_outline_requires_actual_source_url(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(outline_path, page_count=1)
    outline["slides"][0]["evidence"] = [
        "FIFA/权威检索线索确认：巴西曾获得世界杯冠军。"
    ]
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run(
        "validate_outline.js",
        str(outline_path),
        "--min-slides",
        "1",
        "--max-slides",
        "1",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        "must include the actual http(s) source URL" in issue
        for issue in payload["issues"]
    )


def test_outline_rejects_evidence_too_long_for_deck_truth_contract(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(outline_path, page_count=1)
    outline["slides"][0]["evidence"] = [
        f"{'已核实的公开事实。' * 32} | Example | https://example.com/source-a"
    ]
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run(
        "validate_outline.js",
        str(outline_path),
        "--min-slides",
        "1",
        "--max-slides",
        "1",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        "evidence.0 exceeds 280 characters" in issue
        and "split it into separate evidence items" in issue
        for issue in payload["issues"]
    )


def test_public_research_outline_requires_evidence_on_every_slide(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(outline_path, page_count=1)
    outline["slides"][0]["evidence"] = []
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run(
        "validate_outline.js",
        str(outline_path),
        "--min-slides",
        "1",
        "--max-slides",
        "1",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        "requires at least one claim | source | http(s) URL evidence item"
        in issue
        for issue in payload["issues"]
    )


def test_outline_rejects_assumed_private_financing_stage(tmp_path: Path) -> None:
    outline_path = tmp_path / "outline.json"
    outline = _write_outline(
        outline_path,
        page_count=3,
        source_mode="user_provided",
    )
    outline["slides"][0]["evidence"] = [
        "用户提供：计划融资 3000 万元。",
        "假设：融资阶段按早期成长轮 / Pre-A 轮示意表达。",
    ]
    outline_path.write_text(
        json.dumps(outline, ensure_ascii=False),
        encoding="utf-8",
    )

    result = _run("validate_outline.js", str(outline_path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert any(
        "assumes a private identity fact" in issue
        and "financing round" in issue
        for issue in payload["issues"]
    )


def test_outline_data_visual_detection_accepts_cover_and_named_charts(
    tmp_path: Path,
) -> None:
    outline_path = tmp_path / "outline.json"
    slides = [
        {
            "page": 1,
            "title": "AI 制造平台融资路演",
            "message": "本轮计划融资 3000 万元。",
            "bullets": ["产品定位", "融资诉求"],
            "layout": "封面页",
            "visual": "科技制造风背景与融资金额视觉焦点",
            "evidence": ["用户提供：融资 3000 万元。"],
        },
        {
            "page": 2,
            "title": "市场规模",
            "message": "TAM、SAM、SOM 展示分层市场空间。",
            "bullets": ["TAM", "SAM", "SOM"],
            "layout": "市场规模页",
            "visual": "市场规模图，展示 TAM、SAM、SOM",
            "evidence": ["示意：TAM、SAM、SOM。"],
        },
        {
            "page": 3,
            "title": "商业模式",
            "message": "软件订阅收入与交付服务构成收入组合。",
            "bullets": ["订阅", "部署", "服务"],
            "layout": "商业模式页",
            "visual": "三段式收入结构图与客户扩展阶梯图",
            "evidence": ["用户要求：说明收入来源。"],
        },
        {
            "page": 4,
            "title": "业务增长",
            "message": "当前 ARR 达到 800 万元。",
            "bullets": ["试点", "商业化", "扩张"],
            "layout": "业务进展页",
            "visual": "ARR 增长曲线",
            "evidence": ["用户提供：ARR 800 万元。"],
        },
        {
            "page": 5,
            "title": "融资计划",
            "message": "融资 3000 万元用于三类投入。",
            "bullets": ["研发", "销售", "交付"],
            "layout": "融资计划页",
            "visual": "资金用途图，使用环形图展示比例",
            "evidence": ["用户提供：融资 3000 万元。"],
        },
    ]
    outline_path.write_text(
        json.dumps(
            {
                "deck_goal": "完成融资沟通",
                "audience": "投资人",
                "source_mode": "user_provided",
                "storyline": "从项目定位进入市场、商业模式与进展，最后提出融资计划。",
                "slides": slides,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _run("validate_outline.js", str(outline_path))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert not any(
        "appears data-heavy but visual does not name" in warning
        for warning in payload["warnings"]
    )


def test_controlled_finalizer_stops_at_first_failed_dependency(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    deck_path.write_text('{"slides": []}', encoding="utf-8")
    manifest_path = tmp_path / "assets" / "generated" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text('{"mode":"auto","image_plan":[]}', encoding="utf-8")

    result = _run(
        "finalize_controlled_deck.js",
        str(deck_path),
        "--out",
        str(tmp_path / "index.html"),
    )

    assert result.returncode == 1
    assert "FINALIZE_STOP stage=deck_spec" in result.stderr
    assert json.loads((tmp_path / "qa" / "deck_spec.json").read_text())["ok"] is False
    assert not (tmp_path / "qa" / "truth_check.json").exists()
    assert not (tmp_path / "index.html").exists()


def test_controlled_finalizer_runs_compact_complete_chain(tmp_path: Path) -> None:
    deck = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    deck["truth_contract"] = {
        "mode": "illustrative",
        "source_facts": [],
        "research_facts": [],
        "assumptions": ["示例画廊内容仅用于编译器回归测试。"],
    }
    deck_path = tmp_path / "deck.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    manifest_path = tmp_path / "assets" / "generated" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "mode": "auto",
                "image_plan": [
                    {
                        "slide": index,
                        "slide_id": slide["id"],
                        "layout_id": slide["layout_id"],
                        "required": False,
                        "decision": "skip",
                        "status": "skipped",
                        "output_path": None,
                    }
                    for index, slide in enumerate(deck["slides"], start=1)
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        "finalize_controlled_deck.js",
        str(deck_path),
        "--out",
        str(tmp_path / "index.html"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("FINALIZE_PASS stage=") == 6
    assert '"ok":true' in result.stdout
    assert (tmp_path / "index.html").is_file()
    for report_name in (
        "deck_spec.json",
        "truth_check.json",
        "image_manifest.json",
        "html_self_check.json",
        "runtime_probe.json",
    ):
        report = json.loads((tmp_path / "qa" / report_name).read_text())
        assert report["ok"] is True


def test_example_validates_and_renders_deterministically(tmp_path: Path) -> None:
    report = tmp_path / "qa" / "deck_spec.json"
    validation = _run(
        "validate_deck_spec.js",
        str(EXAMPLE),
        "--report",
        str(report),
    )

    assert validation.returncode == 0, validation.stderr
    assert json.loads(report.read_text())["ok"] is True

    first = tmp_path / "first.html"
    second = tmp_path / "second.html"
    first_render = _run("render_deck_html.js", str(EXAMPLE), "--out", str(first))
    second_render = _run("render_deck_html.js", str(EXAMPLE), "--out", str(second))

    assert first_render.returncode == 0, first_render.stderr
    assert second_render.returncode == 0, second_render.stderr
    assert first.read_bytes() == second.read_bytes()

    self_check = _run(
        "html_self_check.js",
        str(first),
        "--dom-to-pptx",
        "--allow-local-images",
    )
    assert self_check.returncode == 0, self_check.stdout + self_check.stderr
    self_check_payload = json.loads(
        self_check.stdout.split("\nHTML self-check:", 1)[0]
    )
    slack_warnings = [
        warning
        for warning in self_check_payload["warnings"]
        if "PowerPoint wrap slack" in warning
    ]
    assert slack_warnings == []

    html = first.read_text(encoding="utf-8")
    rendered_deck = html.split('<section class="deck-layout-picker"', 1)[0]
    assert rendered_deck.count('<section class="slide ') == 7
    assert 'data-layout-id="comparison-two-column-v1"' in html
    assert 'data-deck-composition="institutional-grid"' in html
    assert 'data-deck-composition-variant="ledger-grid"' in html
    assert '"design": {' in html
    assert 'id="deck-document"' in html
    assert 'data-action="save"' in html
    assert 'data-action="add-slide"' in html
    assert 'data-action="layout"' in html
    assert 'data-action="adjust"' in html
    assert 'data-toolbar-menu="design"' in html
    assert 'data-toolbar-menu="page"' in html
    assert 'data-toolbar-menu-trigger' in html
    assert 'role="menu" aria-label="设计操作"' in html
    assert 'role="menu" aria-label="页面操作"' in html
    assert 'data-action="present"' in html
    assert 'aria-label="播放"' in html
    assert ">▶</button>" in html
    assert "▶ 播放" not in html
    assert 'data-action="export-pptx"' in html
    assert 'data-role="thumbnail-list"' in html
    assert 'data-save-state="download"' in html
    assert 'id="deck-layout-picker"' in html
    assert 'id="deck-layout-controls"' in html
    assert 'data-role="present-controls"' in html
    assert 'data-role="present-progress"' in html
    assert 'data-deck-runtime="layout-registry"' in html
    assert 'data-role="current-page"' in html
    assert 'data-role="current-title"' in html
    assert "前移此页" not in html
    assert "后移此页" not in html
    assert "前移</button>" in html
    assert "后移</button>" in html
    assert "已前移" in html
    assert 'class="statement-main has-proofs proofs-metrics"' in html
    assert 'class="proof-index"' in html
    assert "border-radius: 0;" in html
    assert "0 0 0 4px rgba(30, 43, 250" not in html
    assert "navigator.webdriver" in html
    assert "box-agent:deck-change" in html
    assert "box-agent-controlled-deck" in html
    assert "officev3-controlled-deck-host" in html
    assert 'postToHost("save-request"' in html
    assert 'postToHost("export-pptx-request"' in html
    assert 'message.type === "export-pptx-result"' in html
    assert "文件已在外部改变" in html
    assert 'cloneSaveButton.dataset.saveState = "download"' in html
    assert 'emitChange("add-slide")' in html
    assert 'emitChange("change-layout")' in html
    assert '"change-layout-option"' in html
    assert '"add-layout-item"' in html
    assert '"delete-layout-item"' in html
    assert '"move-layout-item"' in html
    assert "event.stopPropagation();" in html
    assert "clickPath.includes(layoutControls)" in html
    assert "function enterPresentation()" in html
    assert "function exitPresentation(" in html
    assert "function updateEditorScale()" in html
    assert "function renderThumbnails()" in html
    assert "deck-thumbnails-visible" in html
    assert '(min-width: 1080px) and (min-height: 560px)' in html
    assert 'menu.addEventListener("pointerenter"' in html
    assert 'menu.addEventListener("focusin"' in html
    assert "function scheduleToolbarMenuClose(menu)" in html
    assert 'class="toolbar-popover-bridge"' in html
    assert 'currentIndex = nextIndex;\n      scrollToCurrent("auto");' in html
    assert 'setProperty("--deck-editor-slide-gap"' in html
    assert 'removeProperty("--deck-editor-scale")' in html
    assert "body.deck-presenting" in html
    assert "body:not(.deck-presenting) #deck-root > .slide" in html
    assert 'data-media-slot="hero"' in html
    assert 'data-layout-region="cover-copy"' in html
    assert "layout_drafts" in html
    assert "切换回来即可恢复" in html
    assert "box-shadow: inset 3px 0 #222222" not in html
    assert "outline: 1px solid #A8A8A2" in html


def test_toolbar_groups_fit_embedded_editor_viewport(tmp_path: Path) -> None:
    html_path = tmp_path / "toolbar.html"
    render = _run("render_deck_html.js", str(EXAMPLE), "--out", str(html_path))
    assert render.returncode == 0, render.stderr

    probe = _run(
        "probe_deck_runtime.js",
        str(html_path),
        "--viewport",
        "1100x800",
    )
    if probe.returncode != 0 and (
        "Cannot find module 'playwright'" in probe.stderr
        or "Executable doesn't exist" in probe.stderr
    ):
        pytest.skip("Managed Playwright browser is unavailable")

    assert probe.returncode == 0, probe.stderr or probe.stdout
    runtime = json.loads(probe.stdout)
    assert runtime["ok"] is True
    assert runtime["editor"]["thumbnailsVisible"] is True
    assert runtime["editor"]["toolbar"]["hasOverflow"] is False
    assert runtime["editor"]["toolbar"]["left"] >= 0
    assert runtime["editor"]["toolbar"]["right"] <= 1100
    assert runtime["editor"]["toolbarMenus"] == {
        "design": {"available": True, "open": True, "expanded": True},
        "page": {"available": True, "open": True, "expanded": True},
    }


def test_project_case_layout_renders_metrics_and_two_compositions(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "project-case-study-v1",
        "project-case-study-v1",
        "--theme",
        "block-frame",
        "--title",
        "Portfolio",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text())
    deck["slides"][0]["props"].update(
        {
            "title": "品牌项目 A（待补充）",
            "positioning": "品牌识别与数字体验的系统化升级。",
            "metrics": [
                {"value": "待补充", "label": "业务结果"},
                {"value": "待补充", "label": "设计影响"},
            ],
            "composition": "split",
            "media_side": "left",
        }
    )
    deck["slides"][1]["props"].update(
        {
            "title": "品牌项目 B（待补充）",
            "positioning": "从叙事策略到发布体验的一体化设计。",
            "metrics": [
                {"value": "待补充", "label": "触达范围"},
                {"value": "待补充", "label": "后续表现"},
            ],
            "composition": "poster",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "index.html"

    validation = _run("validate_deck_spec.js", str(deck_path))
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))

    assert validation.returncode == 0, validation.stdout
    assert rendered.returncode == 0, rendered.stderr
    html = html_path.read_text(encoding="utf-8")
    assert "layout-project-case project-split media-left" in html
    assert "layout-project-case project-poster media-right" in html
    assert 'data-prop-path="metrics.0.value"' in html
    assert "项目视觉 · 双击替换" in html


def test_extended_layouts_render_editable_data_and_semantic_variants(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "cover-editorial-v1",
        "text-columns-v1",
        "chart-bar-v1",
        "table-data-v1",
        "closing-next-steps-v1",
        "cards-grid-v1",
        "--title",
        "Extended layout gallery",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "alignment": "center",
            "tags": ["团队协作", "Skill 生态", "移动端任务", "付费积分"],
        }
    )
    deck["slides"][1]["props"].update(
        {
            "variant": "lead",
            "sections": [
                {
                    "label": "01",
                    "title": "核心判断",
                    "body": "主文本承担完整叙事，并与右侧补充信息形成清晰主次。",
                    "bullets": ["证据一", "证据二"],
                },
                {
                    "label": "02",
                    "title": "背景",
                    "body": "补充必要背景。",
                    "bullets": [],
                },
                {
                    "label": "03",
                    "title": "影响",
                    "body": "说明判断带来的影响。",
                    "bullets": [],
                },
            ],
        }
    )
    deck["slides"][2]["props"].update(
        {
            "variant": "columns",
            "insight": (
                "市场规模图为示意：分层数据用于表达从总体市场到优先可服务市场的递进关系。"
            ),
            "source": (
                "来源：用户提供的市场方向；具体数值为演示假设，交付前应替换为正式数据。"
            ),
            "items": [
                {"label": "A", "value": "82%", "note": "领先"},
                {"label": "B", "value": "64%", "note": ""},
                {"label": "C", "value": "47%", "note": ""},
                {"label": "D", "value": "31%", "note": ""},
            ],
        }
    )
    deck["slides"][3]["props"].update(
        {
            "variant": "comparison",
            "columns": ["项目", "A", "B", "C", "建议"],
            "rows": [
                ["成本", "低", "中", "高", "A"],
                ["速度", "快", "中", "慢", "A"],
            ],
        }
    )
    deck["slides"][4]["props"]["variant"] = "contact"
    deck["slides"][5]["props"].update(
        {
            "variant": "numbered",
            "items": [
                {
                    "kicker": f"{index:02d}",
                    "title": f"议题 {index}",
                    "body": "用于验证自动序号不会与数字标签重复。",
                }
                for index in range(1, 7)
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "index.html"
    report_path = tmp_path / "html_self_check.json"

    validation = _run("validate_deck_spec.js", str(deck_path))
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    self_check = _run(
        "html_self_check.js",
        str(html_path),
        "--dom-to-pptx",
        "--allow-local-images",
        "--report",
        str(report_path),
    )

    assert validation.returncode == 0, validation.stdout
    assert rendered.returncode == 0, rendered.stderr
    assert self_check.returncode == 0, self_check.stdout
    self_check_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert self_check_report["issues"] == []
    assert not any(
        "PowerPoint wrap slack" in warning
        for warning in self_check_report["warnings"]
    )
    assert not any(
        "short background text uses vertical padding" in warning
        for warning in self_check_report["warnings"]
    )
    html = html_path.read_text(encoding="utf-8")
    assert "layout-cover-editorial cover-editorial-center" in html
    assert 'data-prop-path="tags.3"' in html
    assert "editorial-cover-tags" in html
    assert "layout-text-columns text-lead text-count-3" in html
    assert "layout-chart-bar chart-columns chart-count-4" in html
    assert "data-pptx-chart" in html
    assert "data-chart-spec=" in html
    assert 'data-native-chart="true"' in html
    assert 'data-deck-runtime="echarts" data-echarts-version="6.0.0"' in html
    assert 'data-deck-runtime="chart-runtime"' in html
    assert "layout-data-table table-comparison table-columns-5" in html
    assert '<th><span class="data-table-cell-text"' in html
    assert 'data-prop-path="rows.0.4"' in html
    assert "layout-closing closing-contact" in html
    assert "layout-cards cards-numbered cards-count-6" in html
    assert (
        'class="card-kicker" data-prop-path="items.0.kicker" '
        'data-prop-kind="text"></p>'
    ) in html
    assert ".cards-numbered .cards-grid::before" in html
    assert "display: none;" in html


def test_closing_summary_keeps_editable_pptx_wrap_slack(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "closing-next-steps-v1",
        "--title",
        "Closing wrap regression",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "variant": "next-steps",
            "title": "未来看点：如何从新星走向核心",
            "subtitle": (
                "亚马尔下一阶段的关键词，是稳定输出、身体管理、战术承担和在俱乐部/"
                "国家队双线成为核心。"
            ),
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "index.html"
    report_path = tmp_path / "html_self_check.json"

    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    self_check = _run(
        "html_self_check.js",
        str(html_path),
        "--dom-to-pptx",
        "--allow-local-images",
        "--report",
        str(report_path),
    )

    assert rendered.returncode == 0, rendered.stderr
    assert self_check.returncode == 0, self_check.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert not any(
        "PowerPoint wrap slack" in warning for warning in report["warnings"]
    )


def test_animated_chart_layout_supports_seven_types_and_editable_matrix(
    tmp_path: Path,
) -> None:
    chart_types = ["bar", "column", "line", "area", "pie", "donut", "radar"]
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        *(["chart-data-v1"] * len(chart_types)),
        "--title",
        "Animated chart gallery",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    for slide, chart_type in zip(deck["slides"], chart_types, strict=True):
        slide["props"].update(
            {
                "chart_type": chart_type,
                "categories": ["Q1", "Q2", "Q3", "Q4"],
                "series": [
                    {"name": "本期", "values": ["42", "58", "71", "86"]},
                    {"name": "上期", "values": ["34", "49", "57", "69"]},
                ],
                "animation": "on",
            }
        )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "index.html"
    report_path = tmp_path / "html_self_check.json"

    validation = _run("validate_deck_spec.js", str(deck_path))
    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    self_check = _run(
        "html_self_check.js",
        str(html_path),
        "--report",
        str(report_path),
    )

    assert validation.returncode == 0, validation.stdout
    assert rendered.returncode == 0, rendered.stderr
    assert self_check.returncode == 0, self_check.stdout
    html = html_path.read_text(encoding="utf-8")
    assert html.count('data-echarts-version="6.0.0"') == 1
    assert html.count('<section class="slide layout-chart-data') == len(chart_types)
    assert html.count('data-native-chart="true"') >= len(chart_types)
    assert html.count('data-chart-canvas') >= len(chart_types)
    for chart_type in chart_types:
        assert f"chart-type-{chart_type}" in html
    assert "createChartDataControl" in html
    assert "add-chart-category" in html
    assert "add-chart-series" in html
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["issues"] == []


def test_mixed_unit_chart_uses_independent_editable_small_multiples(
    tmp_path: Path,
) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "chart-data-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "chart_type": "column",
            "categories": ["首次响应时间", "一次解决率", "满意度"],
            "series": [
                {"name": "改进前", "values": ["18", "68%", "4.2"]},
                {"name": "改进后", "values": ["7", "81%", "4.6"]},
            ],
            "legend": "on",
            "show_values": "on",
            "animation": "on",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "index.html"
    report_path = tmp_path / "html_self_check.json"

    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    self_check = _run(
        "html_self_check.js",
        str(html_path),
        "--dom-to-pptx",
        "--report",
        str(report_path),
    )

    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    assert self_check.returncode == 0, self_check.stdout + self_check.stderr
    html = html_path.read_text(encoding="utf-8")
    rendered_markup = html.split('<script data-deck-runtime="layout-registry">', 1)[0]
    assert 'data-chart-scale="independent"' in html
    assert "chart-small-multiples-count-3" in html
    assert rendered_markup.count('data-native-chart="true"') == 3
    assert rendered_markup.count('class="echarts-for-pptx"') == 3
    assert "chart-small-multiple-legend" in html
    assert "&quot;value_suffix&quot;:&quot;%&quot;" in html
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["issues"] == []


def test_bodyless_timeline_uses_title_sequence_density_mode(tmp_path: Path) -> None:
    deck_path = tmp_path / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "timeline-horizontal-v1",
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "title": "采取的行动",
            "steps": [
                {"phase": "知识沉淀", "title": "统一知识库", "body": ""},
                {"phase": "工单匹配", "title": "工单自动分流", "body": ""},
                {"phase": "质量复盘", "title": "每周质检复盘", "body": ""},
            ],
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "index.html"
    report_path = tmp_path / "html_self_check.json"

    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    self_check = _run(
        "html_self_check.js",
        str(html_path),
        "--dom-to-pptx",
        "--report",
        str(report_path),
    )

    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    assert self_check.returncode == 0, self_check.stdout + self_check.stderr
    html = html_path.read_text(encoding="utf-8")
    assert "timeline-count-3 timeline-bodyless" in html
    assert "body[data-deck-composition] .layout-timeline.timeline-bodyless .timeline-step" in html
    assert "justify-content: center" in html
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["issues"] == []


def test_editable_pptx_chart_export_preserves_cjk_font_fallbacks() -> None:
    bundle = (SCRIPTS_DIR / "dom-to-pptx.bundle.js").read_text(encoding="utf-8")

    assert "resolvePptxFontFace(style.fontFamily, text)" in bundle
    assert "getTextStyle(nodeStyle, config.scale, textVal)" in bundle
    assert "const chartText = [...spec.categories" in bundle
    assert "legendFontFace: bodyFont" in bundle
    assert "catAxisLabelFontFace: bodyFont" in bundle


def test_block_frame_theme_renders_builtin_visual_dna(tmp_path: Path) -> None:
    deck = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    deck["theme_id"] = "block-frame"
    deck["slides"][2]["props"]["emphasis"] = "poster"
    deck_path = tmp_path / "block-frame.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "block-frame.html"

    validation = _run("validate_deck_spec.js", str(deck_path))
    render = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))

    assert validation.returncode == 0, validation.stdout
    assert render.returncode == 0, render.stderr
    html = html_path.read_text(encoding="utf-8")
    assert 'data-deck-theme="block-frame"' in html
    assert "--deck-bg: #FFFDF5" in html
    assert "--deck-border-width: 5px" in html
    assert html.index("--deck-bg: #FDFAE7") < html.rindex("--deck-bg: #FFFDF5")
    assert 'body[data-deck-theme="block-frame"] .slide' in html
    assert "box-shadow: 12px 12px 0 var(--deck-text)" in html
    assert 'body[data-deck-theme="block-frame"] .statement-poster' in html
    assert "background-color: var(--deck-primary);" in html
    assert "color: var(--deck-inverse);" in html
    assert 'body[data-deck-theme="block-frame"] .layout-timeline' in html

    probe = _run(
        "probe_deck_runtime.js",
        str(html_path),
        "--viewport",
        "1440x900",
    )
    if probe.returncode != 0 and (
        "Cannot find module 'playwright'" in probe.stderr
        or "Executable doesn't exist" in probe.stderr
    ):
        pytest.skip("Managed Playwright browser is unavailable")
    assert probe.returncode == 0, probe.stderr or probe.stdout
    runtime = json.loads(probe.stdout)
    assert runtime["ok"] is True
    assert runtime["editor"]["primary"] == "#FE90E8"
    assert runtime["editor"]["inverse"] == "#000000"
    assert runtime["editor"]["editorScale"] < 1
    assert runtime["editor"]["statement"]["contrast"] >= 4.5
    assert runtime["export"] == {
        "cssWidth": 1920,
        "cssHeight": 1080,
        "renderedWidth": 1920,
        "renderedHeight": 1080,
    }


def test_mono_blue_block_frame_reuses_visual_dna_with_restrained_palette(
    tmp_path: Path,
) -> None:
    deck = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    deck["theme_id"] = "block-frame-mono-blue"
    deck["slides"][2]["props"]["emphasis"] = "poster"
    deck_path = tmp_path / "mono-blue.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "mono-blue.html"

    validation = _run("validate_deck_spec.js", str(deck_path))
    render = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))

    assert validation.returncode == 0, validation.stdout
    assert render.returncode == 0, render.stderr
    html = html_path.read_text(encoding="utf-8")
    assert 'data-deck-theme="block-frame"' in html
    assert 'data-deck-theme-id="block-frame-mono-blue"' in html
    assert "--deck-bg: #FFFDF7" in html
    assert "--deck-surface: #FFFFFF" in html
    assert "--deck-primary: #1E2BFA" in html
    assert "--deck-primary-soft: #E3E6FF" in html
    assert "--deck-inverse: #FFFFFF" in html
    assert "#FE90E8" not in html[html.rindex(":root {") :]

    probe = _run(
        "probe_deck_runtime.js",
        str(html_path),
        "--viewport",
        "1440x900",
    )
    if probe.returncode != 0 and (
        "Cannot find module 'playwright'" in probe.stderr
        or "Executable doesn't exist" in probe.stderr
    ):
        pytest.skip("Managed Playwright browser is unavailable")
    assert probe.returncode == 0, probe.stderr or probe.stdout
    runtime = json.loads(probe.stdout)
    assert runtime["ok"] is True
    assert runtime["editor"]["primary"] == "#1E2BFA"
    assert runtime["editor"]["inverse"] == "#FFFFFF"
    assert runtime["editor"]["statement"]["contrast"] >= 4.5


def test_validation_errors_expose_registered_contract_choices(tmp_path: Path) -> None:
    deck = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    deck["theme_id"] = "not-a-theme"
    deck["slides"][0]["props"]["image"] = "assets/generated/cover.png"
    deck_path = tmp_path / "actionable-errors.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_spec.js", str(deck_path))

    assert result.returncode == 1
    assert "registered theme_ids: 8-bit-orbit, biennale-yellow" in result.stdout
    assert "signal" in result.stdout
    assert "studio" in result.stdout
    assert "vellum" in result.stdout
    assert "allowed fields for cover-hero-v1" in result.stdout
    assert "hero" in result.stdout


def test_slide_background_is_validated_normalized_and_rendered(tmp_path: Path) -> None:
    deck = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    deck["slides"][0]["background"] = {
        "src": "assets/generated/cover-background.png",
        "alt": "Abstract workflow atmosphere",
        "origin": "generated",
        "treatment": "wash-dark",
    }
    deck_path = tmp_path / "background.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "background.html"

    validation = _run("validate_deck_spec.js", str(deck_path))
    render = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))

    assert validation.returncode == 0, validation.stdout
    assert render.returncode == 0, render.stderr
    html = html_path.read_text(encoding="utf-8")
    assert "has-background background-wash-dark" in html
    assert 'data-background-origin="generated"' in html
    assert 'src="assets/generated/cover-background.png"' in html
    assert 'data-model-root="slide" data-prop-path="background.src"' in html
    assert '"fit": "cover"' in html
    assert '"position": "center"' in html
    assert (
        ".slide-background::after {\n"
        "  content: \"\";\n"
        "  position: absolute;\n"
        "  inset: 0;\n"
        "  background: var(--deck-bg);\n"
        "  opacity: 0.7;"
    ) in html
    assert "background: rgba(253, 250, 231, 0.7);" not in html
    assert (
        ".slide.background-wash-dark .slide-background::after {\n"
        "  background: #0D0E12;\n"
        "  opacity: 0.64;"
    ) in html


def test_statement_auto_uses_wrapping_points_for_sentence_values(tmp_path: Path) -> None:
    deck = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    statement = deck["slides"][2]["props"]
    statement["proofs"] = [
        {"label": "事实边界", "value": "不预设未发生赛果"},
        {"label": "后续更新", "value": "保留对阵产生后的替换空间"},
        {"label": "使用场景", "value": "适合汇报、活动策划和内容预热"},
    ]
    deck_path = tmp_path / "points.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = tmp_path / "points.html"

    validation = _run("validate_deck_spec.js", str(deck_path))
    render = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))

    assert validation.returncode == 0, validation.stdout
    assert render.returncode == 0, render.stderr
    html = html_path.read_text(encoding="utf-8")
    assert 'class="statement-main has-proofs proofs-points"' in html
    assert "不预设未发生赛果" in html


@pytest.mark.parametrize("family", ["analytical-exhibit", "technical-schematic"])
def test_statement_points_keep_full_width_in_structured_families(
    tmp_path: Path,
    family: str,
) -> None:
    deck_path = tmp_path / family / "deck.json"
    scaffold = _run(
        "inspect_deck_contract.js",
        "statement-focus-v1",
        "--theme",
        "blue-professional",
        "--family",
        family,
        "--out",
        str(deck_path),
    )
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck["slides"][0]["props"].update(
        {
            "eyebrow": "持续看点",
            "statement": "为什么值得关注：EURO 2024后的持续看点",
            "support": (
                "UEFA将他评为EURO 2024 Young Player of the Tournament，"
                "说明其表现已经从俱乐部延伸到国家队大赛舞台。"
            ),
            "proofs": [
                {"label": "", "value": "UEFA官方奖项：EURO 2024最佳年轻球员。"},
                {"label": "", "value": "关注已验证成就，避免媒体猜测。"},
                {"label": "", "value": "表述为高潜力、仍在发展中。"},
            ],
            "proof_style": "points",
        }
    )
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    html_path = deck_path.parent / "index.html"
    report_path = deck_path.parent / "qa" / "html_self_check.json"

    rendered = _run("render_deck_html.js", str(deck_path), "--out", str(html_path))
    self_check = _run(
        "html_self_check.js",
        str(html_path),
        "--dom-to-pptx",
        "--allow-local-images",
        "--report",
        str(report_path),
    )

    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    assert self_check.returncode == 0, self_check.stdout + self_check.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["issues"] == []
    assert not any("overflow detected" in warning for warning in report["warnings"])
    assert not any(
        "PowerPoint wrap slack" in warning for warning in report["warnings"]
    )


def test_image_manifest_rejects_duplicate_generated_assets_and_checks_deck_refs(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "assets" / "generated"
    generated.mkdir(parents=True)
    (generated / "a.png").write_bytes(b"same-image")
    (generated / "b.png").write_bytes(b"same-image")
    manifest = generated / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "mode": "creative_image_mode",
                "image_plan": [
                    {
                        "slide": 1,
                        "decision": "generate",
                        "status": "generated",
                        "output_path": "assets/generated/a.png",
                    },
                    {
                        "slide": 2,
                        "decision": "generate",
                        "status": "generated",
                        "output_path": "assets/generated/b.png",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    deck = tmp_path / "deck.json"
    deck.write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "props": {
                            "image": {
                                "src": "assets/generated/a.png",
                                "origin": "generated",
                            }
                        }
                    },
                    {
                        "props": {
                            "image": {
                                "src": "assets/generated/b.png",
                                "origin": "generated",
                            }
                        }
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    duplicate = _run(
        "validate_image_manifest.js",
        str(manifest),
        "--mode",
        "creative_image_mode",
        "--min-generated",
        "2",
        "--deck",
        str(deck),
    )
    assert duplicate.returncode == 1
    assert "reused across multiple image-plan entries" in duplicate.stdout

    (generated / "b.png").write_bytes(b"different-image")
    valid = _run(
        "validate_image_manifest.js",
        str(manifest),
        "--mode",
        "creative_image_mode",
        "--min-generated",
        "2",
        "--deck",
        str(deck),
    )
    assert valid.returncode == 0, valid.stdout


def test_auto_image_manifest_rejects_unresolved_generate_entry(tmp_path: Path) -> None:
    generated = tmp_path / "assets" / "generated"
    generated.mkdir(parents=True)
    manifest = generated / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "mode": "auto",
                "image_plan": [
                    {
                        "slide": 1,
                        "decision": "generate",
                        "status": "pending",
                        "output_path": "assets/generated/missing.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run("validate_image_manifest.js", str(manifest))

    assert result.returncode == 1
    assert "generate entry is unresolved" in result.stdout


def test_sync_image_manifest_status_marks_existing_assets_once(tmp_path: Path) -> None:
    generated = tmp_path / "assets" / "generated"
    generated.mkdir(parents=True)
    (generated / "new.png").write_bytes(b"new-image")
    (generated / "fixed.png").write_bytes(b"fixed-image")
    manifest = generated / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "auto",
                "image_plan": [
                    {
                        "slide": 1,
                        "decision": "generate",
                        "status": "pending",
                        "decision_reason": "cover visual",
                        "output_path": "assets/generated/new.png",
                    },
                    {
                        "slide": 2,
                        "decision": "use_existing",
                        "status": "pending",
                        "output_path": "assets/generated/fixed.png",
                    },
                    {
                        "slide": 3,
                        "decision": "skip",
                        "status": "skipped",
                        "output_path": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    first = _run("sync_image_manifest_status.js", str(manifest))
    second = _run("sync_image_manifest_status.js", str(manifest))

    assert first.returncode == 0, first.stderr
    assert '"changed": 2' in first.stdout
    assert second.returncode == 0, second.stderr
    assert '"changed": 0' in second.stdout
    payload = json.loads(manifest.read_text())
    assert payload["image_plan"][0]["status"] == "generated"
    assert payload["image_plan"][0]["decision_reason"] == "cover visual"
    assert payload["image_plan"][1]["status"] == "ready"
    assert payload["image_plan"][2]["status"] == "skipped"


def test_sync_image_manifest_status_rejects_missing_generated_asset(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "assets" / "generated"
    generated.mkdir(parents=True)
    manifest = generated / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "image_plan": [
                    {
                        "slide": 1,
                        "decision": "generate",
                        "status": "pending",
                        "output_path": "assets/generated/missing.png",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _run("sync_image_manifest_status.js", str(manifest))

    assert result.returncode == 1
    assert "Cannot mark unresolved generated image" in result.stderr
    assert json.loads(manifest.read_text())["image_plan"][0]["status"] == "pending"


def test_comparison_layout_uses_flat_editorial_rules() -> None:
    css = (SKILL_DIR / "runtime" / "deck.css").read_text(encoding="utf-8")
    column_block = css.split(".comparison-column {", 1)[1].split("}", 1)[0]
    right_block = css.split(".comparison-right {", 1)[1].split("}", 1)[0]

    assert "border-radius: 0;" in column_block
    assert "border-top: var(--deck-border-width) solid var(--deck-border);" in column_block
    assert "border-bottom: var(--deck-border-width) solid var(--deck-border);" in column_block
    assert "background: transparent;" in column_block
    assert "var(--deck-primary)" not in right_block
    assert "background: transparent;" in right_block


def test_auto_image_manifest_rejects_skipping_a_required_cover(tmp_path: Path) -> None:
    generated = tmp_path / "assets" / "generated"
    generated.mkdir(parents=True)
    manifest = generated / "manifest.json"
    payload = {
        "mode": "auto",
        "image_plan": [
            {
                "slide": 1,
                "required": True,
                "decision": "skip",
                "status": "skipped",
                "output_path": None,
            }
        ],
    }
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    skipped = _run("validate_image_manifest.js", str(manifest))

    assert skipped.returncode == 1
    assert "required image entry is unresolved" in skipped.stdout

    fixed = generated / "fixed-cover.png"
    fixed.write_bytes(b"fixed-cover")
    payload["image_plan"][0].update(
        {
            "decision": "use_existing",
            "status": "fixed",
            "output_path": "assets/generated/fixed-cover.png",
        }
    )
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    accepted = _run("validate_image_manifest.js", str(manifest))

    assert accepted.returncode == 0, accepted.stdout


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (
            lambda deck: deck["slides"][0]["props"].__setitem__("unknown", "x"),
            "unknown field(s): unknown",
        ),
        (
            lambda deck: deck["slides"][0]["props"].__setitem__("title", "超" * 73),
            "exceeds maxChars 72",
        ),
        (
            lambda deck: deck["slides"][0]["props"].__setitem__(
                "hero", {"src": "https://example.com/hero.png", "alt": "hero"}
            ),
            "remote or executable URLs are not allowed",
        ),
        (
            lambda deck: deck["slides"][0].__setitem__(
                "layout_drafts", {"not-a-layout": {}}
            ),
            "layout_drafts.not-a-layout: unknown layout",
        ),
        (
            lambda deck: deck["slides"][0].__setitem__(
                "background", {"src": "https://example.com/background.png"}
            ),
            "background.src: remote or executable URLs are not allowed",
        ),
        (
            lambda deck: deck["slides"][0].__setitem__(
                "background", {"src": "assets/background.png", "origin": "magic"}
            ),
            "background.origin: expected one of generated, asset, uploaded",
        ),
    ],
)
def test_deck_validation_rejects_unsafe_or_out_of_contract_props(
    tmp_path: Path,
    mutate,
    expected_error: str,
) -> None:
    deck = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    mutate(deck)
    deck_path = tmp_path / "invalid.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")

    result = _run("validate_deck_spec.js", str(deck_path))

    assert result.returncode == 1
    assert expected_error in result.stdout
