"""Unit tests for the text watermark renderer."""

import builtins
import io

import pytest
from PIL import Image

from box_agent.tools import watermark
from box_agent.tools.watermark import apply_text_watermark


def _make_png(size=(640, 480), color=(30, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _make_jpeg(size=(400, 300), color=(220, 220, 220)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def _make_webp(size=(300, 300), color=(200, 50, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "WEBP")
    return buf.getvalue()


def test_watermark_applied_changes_png_bytes_but_keeps_size() -> None:
    original = _make_png()
    out, status = apply_text_watermark(original, "image/png")

    assert status["applied"] is True
    assert status["reason"] is None
    assert out != original
    # Still a valid, same-sized PNG.
    reopened = Image.open(io.BytesIO(out))
    assert reopened.size == (640, 480)


def test_watermark_custom_text_applies() -> None:
    original = _make_png()
    out, status = apply_text_watermark(original, "image/png", "品牌名 2026")

    assert status["applied"] is True
    assert out != original


def test_watermark_skips_svg() -> None:
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    out, status = apply_text_watermark(svg, "image/svg+xml")

    assert status["applied"] is False
    assert "unsupported mime" in status["reason"]
    assert out == svg


def test_watermark_skips_gif() -> None:
    out, status = apply_text_watermark(b"GIF89a-bytes", "image/gif")

    assert status["applied"] is False
    assert out == b"GIF89a-bytes"


def test_watermark_jpeg_output_has_no_alpha() -> None:
    original = _make_jpeg()
    out, status = apply_text_watermark(original, "image/jpeg")

    assert status["applied"] is True
    reopened = Image.open(io.BytesIO(out))
    assert reopened.mode == "RGB"  # flattened, no alpha


def test_watermark_webp_applies() -> None:
    original = _make_webp()
    out, status = apply_text_watermark(original, "image/webp")

    assert status["applied"] is True
    assert out != original


def test_watermark_corrupt_bytes_degrades_gracefully() -> None:
    out, status = apply_text_watermark(b"not an image", "image/png")

    assert status["applied"] is False
    assert "watermark error" in status["reason"]
    assert out == b"not an image"


def test_watermark_missing_pillow_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = b"\x89PNG fake"
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PIL" or name.startswith("PIL."):
            raise ImportError("No module named 'PIL'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out, status = apply_text_watermark(original, "image/png")

    assert status["applied"] is False
    assert "Pillow" in status["reason"]
    assert out == original


def test_resolve_font_uses_bundled_cjk_font() -> None:
    # The bundled Noto Sans SC font ships with the package.
    assert watermark._BUNDLED_FONT.exists()
    font, name = watermark._resolve_font(40)
    assert name == watermark._BUNDLED_FONT.name


def test_resolve_font_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Bundled font missing and no system candidate exists → load_default, no crash.
    monkeypatch.setattr(watermark, "_BUNDLED_FONT", tmp_path / "missing-font.otf")
    monkeypatch.setattr(watermark, "_SYSTEM_FONT_CANDIDATES", ())

    font, name = watermark._resolve_font(40)
    assert name == "load_default"
    assert font is not None


def test_hex_to_rgba_parses_and_clamps() -> None:
    assert watermark._hex_to_rgba("#FFFFFF", 0.5) == (255, 255, 255, 127)
    assert watermark._hex_to_rgba("#000000", 1.0) == (0, 0, 0, 255)
    # invalid hex → white fallback
    assert watermark._hex_to_rgba("not-a-color", 1.0) == (255, 255, 255, 255)
    # opacity clamped to [0, 1]
    assert watermark._hex_to_rgba("#FFFFFF", 5.0)[3] == 255
    assert watermark._hex_to_rgba("#FFFFFF", -1.0)[3] == 0


def test_contrast_stroke_picks_opposite() -> None:
    # light fill → dark stroke
    assert watermark._contrast_stroke((255, 255, 255, 200))[:3] == (0, 0, 0)
    # dark fill → light stroke
    assert watermark._contrast_stroke((0, 0, 0, 200))[:3] == (255, 255, 255)
