#!/usr/bin/env python3
"""Render deterministic text overlays for football-event poster outputs.

Usage:
  python scripts/render_text_overlay.py --image poster-textless.png --config examples/text-overlay-config-example.json --output poster-final.png
  python scripts/render_text_overlay.py --image poster-textless.png --config examples/text-overlay-config-example.json --output poster-final.png --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter, UnidentifiedImageError

SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".webp"}
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


class OverlayError(Exception):
    def __init__(self, code: str, location: str, reason: str, suggestion: str):
        super().__init__(reason)
        self.code = code
        self.location = location
        self.reason = reason
        self.suggestion = suggestion


def fail(code: str, location: str, reason: str, suggestion: str) -> None:
    raise OverlayError(code, location, reason, suggestion)


def print_error(err: OverlayError) -> None:
    print(f"错误码：{err.code}", file=sys.stderr)
    print(f"问题位置：{err.location}", file=sys.stderr)
    print(f"原因：{err.reason}", file=sys.stderr)
    print(f"建议：{err.suggestion}", file=sys.stderr)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail("ERR_FILE_NOT_FOUND", str(path), "配置文件不存在。", "请检查路径是否正确，建议使用绝对路径。")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail("ERR_CONFIG_JSON_INVALID", f"{path}:{exc.lineno}:{exc.colno}", exc.msg, "请检查逗号、引号、括号是否完整，JSON 不支持注释。")


def require_number(value: Any, field: str, min_v: float, max_v: float) -> float:
    if not isinstance(value, (int, float)):
        fail("ERR_CONFIG_VALUE_RANGE", field, f"当前值 {value!r} 不是数字。", f"请将 {field} 设置为 {min_v} 到 {max_v} 之间的数字。")
    v = float(value)
    if not min_v <= v <= max_v:
        fail("ERR_CONFIG_VALUE_RANGE", field, f"当前值 {value!r} 超出允许范围。", f"请将 {field} 设置为 {min_v} 到 {max_v} 之间。")
    return v


def validate_layer(layer: dict[str, Any], index: int) -> None:
    loc = f"text_layers[{index}]"
    if not isinstance(layer, dict):
        fail("ERR_CONFIG_VALUE_RANGE", loc, "文本层必须是对象。", "请参考 examples/text-overlay-config-example.json。")
    if not str(layer.get("text", "")).strip():
        fail("ERR_CONFIG_FIELD_MISSING", f"{loc}.text", "缺少必填字段 text。", "请为该文本层填写需要叠加的文字。")
    require_number(layer.get("font_size", 72), f"{loc}.font_size", 12, 220)
    for axis in ("x", "y"):
        value = layer.get(axis, 0.5 if axis == "x" else 0.1)
        if isinstance(value, float):
            require_number(value, f"{loc}.{axis}", 0, 1)
        elif isinstance(value, int):
            require_number(value, f"{loc}.{axis}", -4096, 4096)
        else:
            fail("ERR_CONFIG_VALUE_RANGE", f"{loc}.{axis}", f"当前值 {value!r} 类型不支持。", "请使用 0-1 的小数百分比或像素整数。")
    if layer.get("align", "center") not in {"left", "center", "right"}:
        fail("ERR_CONFIG_VALUE_RANGE", f"{loc}.align", "align 仅支持 left/center/right。", "请改为 left、center 或 right。")
    if "opacity" in layer:
        require_number(layer["opacity"], f"{loc}.opacity", 0, 1)
    if "stroke_width" in layer:
        require_number(layer["stroke_width"], f"{loc}.stroke_width", 0, 30)
    if "shadow" in layer and isinstance(layer["shadow"], dict) and "blur" in layer["shadow"]:
        require_number(layer["shadow"]["blur"], f"{loc}.shadow.blur", 0, 80)


def validate_config(cfg: dict[str, Any]) -> None:
    if "text_layers" not in cfg:
        fail("ERR_CONFIG_FIELD_MISSING", "text_layers", "缺少必填字段 text_layers。", "请至少提供一个文本层。")
    if not isinstance(cfg["text_layers"], list) or not cfg["text_layers"]:
        fail("ERR_CONFIG_FIELD_MISSING", "text_layers", "text_layers 必须是非空数组。", "请参考示例配置。")
    for i, layer in enumerate(cfg["text_layers"]):
        validate_layer(layer, i)
    safe = cfg.get("safe_area", {})
    if isinstance(safe, dict) and "margin" in safe:
        margin = safe["margin"]
        if isinstance(margin, float):
            require_number(margin, "safe_area.margin", 0, 0.3)
        elif isinstance(margin, int):
            require_number(margin, "safe_area.margin", 0, 600)
        else:
            fail("ERR_CONFIG_VALUE_RANGE", "safe_area.margin", "margin 类型不支持。", "请使用 0-0.3 的小数或像素整数。")


def load_font(size: int, layer: dict[str, Any], warnings: list[str]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[str] = []
    if layer.get("font_path"):
        candidates.append(str(layer["font_path"]))
    if layer.get("font_fallback") and isinstance(layer["font_fallback"], list):
        candidates.extend(str(x) for x in layer["font_fallback"])
    candidates.extend(FONT_CANDIDATES)
    for item in candidates:
        if item and Path(item).exists():
            try:
                if item != layer.get("font_path"):
                    warnings.append(f"WARN_FONT_FALLBACK: 已使用可用字体 {item}")
                return ImageFont.truetype(item, size=size)
            except Exception:
                continue
    warnings.append("WARN_FONT_FALLBACK: 未找到指定字体，已使用 Pillow 默认字体；中文显示可能受限。")
    # ERR_FONT_NOT_FOUND is downgraded to WARN_FONT_FALLBACK when Pillow fallback is available.
    return ImageFont.load_default()


def parse_color(value: str | list[int], field: str, default=(255, 255, 255, 255)):
    if isinstance(value, list):
        if len(value) in {3, 4} and all(isinstance(x, int) and 0 <= x <= 255 for x in value):
            return tuple(value + [255]) if len(value) == 3 else tuple(value)
        fail("ERR_CONFIG_VALUE_RANGE", field, "颜色数组必须为 3 或 4 个 0-255 整数。", "请改为 [255,255,255] 或 #FFFFFF。")
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("#") and len(v) in {7, 9}:
            try:
                r = int(v[1:3], 16); g = int(v[3:5], 16); b = int(v[5:7], 16)
                a = int(v[7:9], 16) if len(v) == 9 else 255
                return (r, g, b, a)
            except ValueError:
                pass
    return default


def text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    return draw.textbbox((0, 0), text, font=font)


def anchor_xy(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, layer: dict[str, Any], canvas_size):
    w, h = canvas_size
    box = text_bbox(draw, text, font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = layer.get("x", 0.5); y = layer.get("y", 0.1)
    if isinstance(x, float): x = int(w * x)
    if isinstance(y, float): y = int(h * y)
    align = layer.get("align", "center")
    if align == "center": x = int(x - tw / 2)
    elif align == "right": x = int(x - tw)
    return int(x), int(y), tw, th


def draw_layer(base: Image.Image, layer: dict[str, Any], safe: dict[str, Any], warnings: list[str]) -> None:
    text = str(layer.get("text", "")).strip()
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(int(layer.get("font_size", 72)), layer, warnings)
    x, y, tw, th = anchor_xy(draw, text, font, layer, base.size)
    margin = safe.get("margin", 0.06)
    margin_px = int(min(base.size) * margin) if isinstance(margin, float) else int(margin)
    if x < margin_px or y < margin_px or x + tw > base.width - margin_px or y + th > base.height - margin_px:
        warnings.append(f"WARN_SAFE_AREA: 文本层 {layer.get('id', text[:8])} 可能超出安全区。")
    shadow = layer.get("shadow")
    if shadow:
        sx = x + int(shadow.get("offset_x", 2)); sy = y + int(shadow.get("offset_y", 2))
        shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_layer)
        sd.text((sx, sy), text, font=font, fill=parse_color(shadow.get("color", "#00000080"), "shadow.color"))
        blur = int(shadow.get("blur", 3))
        if blur > 0: shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
        overlay.alpha_composite(shadow_layer)
    draw.text((x, y), text, font=font, fill=parse_color(layer.get("color", "#FFFFFF"), "color"), stroke_width=int(layer.get("stroke_width", 0)), stroke_fill=parse_color(layer.get("stroke_color", "#000000"), "stroke_color"))
    opacity = float(layer.get("opacity", 1))
    if opacity < 1:
        alpha = overlay.getchannel("A").point(lambda p: int(p * opacity))
        overlay.putalpha(alpha)
    base.alpha_composite(overlay)


def open_image(path: Path) -> Image.Image:
    if not path.exists():
        fail("ERR_FILE_NOT_FOUND", str(path), "输入图片不存在。", "请检查路径是否正确，建议使用绝对路径。")
    if path.suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
        fail("ERR_IMAGE_FORMAT_UNSUPPORTED", str(path), f"不支持的图片格式 {path.suffix}。", "请使用 PNG、JPG、JPEG 或 WEBP。")
    try:
        img = Image.open(path)
    except UnidentifiedImageError:
        fail("ERR_IMAGE_FORMAT_UNSUPPORTED", str(path), "图片无法识别或文件已损坏。", "请重新导出为 PNG/JPG 后再试。")
    if img.mode not in {"RGB", "RGBA"}:
        # ERR_IMAGE_MODE_UNSUPPORTED is handled by safe conversion when possible.
        img = img.convert("RGB")
    return img.convert("RGBA")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dry-run", action="store_true", help="only validate config, image and font availability")
    args = parser.parse_args()
    try:
        image_path = Path(args.image)
        config_path = Path(args.config)
        output_path = Path(args.output)
        cfg = read_json(config_path)
        validate_config(cfg)
        base = open_image(image_path)
        warnings: list[str] = []
        for layer in cfg.get("text_layers", []):
            load_font(int(layer.get("font_size", 72)), layer, warnings)
        if args.dry_run:
            print("PASS: dry-run validation passed")
        else:
            for layer in cfg.get("text_layers", []):
                draw_layer(base, layer, cfg.get("safe_area", {}), warnings)
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                base.convert("RGB").save(output_path, quality=95)
            except OSError as exc:
                fail("ERR_OUTPUT_PATH_INVALID", str(output_path), str(exc), "请更换输出目录或检查写入权限。")
            print(f"PASS: rendered {output_path}")
        for item in dict.fromkeys(warnings):
            print(item)
        return 0
    except OverlayError as err:
        print_error(err)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
