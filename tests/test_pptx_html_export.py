from pathlib import Path


EXPORT_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "box_agent"
    / "skills"
    / "document-skills"
    / "pptx"
    / "scripts"
    / "html_to_editable_pptx.js"
)


def test_source_previews_are_captured_before_export_dom_is_flattened() -> None:
    source = EXPORT_SCRIPT_PATH.read_text(encoding="utf-8")

    preview_capture = source.index(
        "await slideHandles[i].screenshot({ path: imagePath });"
    )
    background_flatten = source.index("await applyDecorationFlatten({")

    assert preview_capture < background_flatten
