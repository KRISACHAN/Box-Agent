#!/usr/bin/env python3
"""渲染一份轻量的人物故事地图 HTML（skill 专用）。

输入：一份 6-Agent 产出的 Markdown（含时间线表 + 地点坐标表）
输出：一个自包含的 HTML，Leaflet + 高德公开瓦片默认底图，并保留 OpenStreetMap 备用图层

不修改主仓库的 profile_page.html——这是 skill 交付的独立轻量视图，
适用于用户需要一个可直接打开、国内网络下更稳定展示底图的静态页面场景。
坐标表仍按 WGS84 保存；使用高德底图显示时，将点位转换为 GCJ-02。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

PI = 3.1415926535897932384626
A = 6378245.0
EE = 0.00669342162296594323


def _out_of_china(lat: float, lon: float) -> bool:
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * abs(x) ** 0.5
    ret += (20.0 * __import__('math').sin(6.0 * x * PI) + 20.0 * __import__('math').sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * __import__('math').sin(y * PI) + 40.0 * __import__('math').sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * __import__('math').sin(y / 12.0 * PI) + 320 * __import__('math').sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * abs(x) ** 0.5
    ret += (20.0 * __import__('math').sin(6.0 * x * PI) + 20.0 * __import__('math').sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * __import__('math').sin(x * PI) + 40.0 * __import__('math').sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * __import__('math').sin(x / 12.0 * PI) + 300.0 * __import__('math').sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat: float, lon: float) -> Tuple[float, float]:
    if _out_of_china(lat, lon):
        return lat, lon
    import math
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    dlon = (dlon * 180.0) / (A / sqrt_magic * math.cos(radlat) * PI)
    return lat + dlat, lon + dlon


TIMELINE_HEADER = re.compile(r"^\|\s*年份?\s*\|(?:[^|\n]+\|)*[^|\n]*事件[^\n]*", re.MULTILINE)
COORD_TABLE_HEADER = re.compile(
    r"^\|[^|\n]*现称[^|\n]*\|[^|\n]*\|[^|\n]*纬度[^|\n]*\|[^|\n]*经度[^\n]*",
    re.MULTILINE,
)


def _parse_timeline(md: str) -> List[Tuple[str, str, str]]:
    """从"生平时间线"markdown 表提取 (年份, 地点, 事件)。

    支持两种表头形态：
        | 年份 | 地点 | 事件 |
        | 年份 | 古称 | 现称 | 事件 |
    """
    rows: List[Tuple[str, str, str]] = []
    match = TIMELINE_HEADER.search(md)
    if not match:
        return rows
    tail = md[match.end():]
    started = False
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            if started:
                break
            continue
        if not line.startswith("|"):
            break
        started = True
        if line.startswith("| ---") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        year = cells[0]
        event = cells[-1]
        place = cells[-2] if len(cells) >= 3 else ""
        if not year or year == "---":
            continue
        rows.append((year, place, event))
    return rows


def _parse_coords(md: str) -> List[Tuple[str, float, float]]:
    """从"地点坐标"markdown 表提取 (地名, 纬度, 经度)。"""
    coords: List[Tuple[str, float, float]] = []
    match = COORD_TABLE_HEADER.search(md)
    if not match:
        return coords
    tail = md[match.end():]
    started = False
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            if started:
                break
            continue
        if not line.startswith("|"):
            break
        started = True
        if line.startswith("| ---") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # 期望列：现称 | 现代搜索地名 | 纬度 | 经度 | 坐标系
        if len(cells) < 4:
            continue
        try:
            lat = float(cells[2])
            lon = float(cells[3])
        except (ValueError, IndexError):
            continue
        coords.append((cells[0], lat, lon))
    return coords


def _parse_short_review(md: str, name: str) -> str:
    for line in md.splitlines():
        if line.startswith("**short_review**") or "short_review" in line.lower():
            _, _, tail = line.partition("：")
            if not tail:
                _, _, tail = line.partition(":")
            return tail.strip().strip("：").strip()
    return f"{name} · 由 1+5 Agent 生成"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{name} · 故事地图</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  body {{ margin: 0; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f8fafc; color: #1e293b; }}
  header {{ padding: 20px 24px; background: linear-gradient(135deg, #0f172a, #1e293b); color: #f8fafc; }}
  header h1 {{ margin: 0 0 6px; font-size: 24px; }}
  header p {{ margin: 0; opacity: 0.85; font-size: 14px; }}
  main {{ display: grid; grid-template-columns: 1fr 360px; gap: 16px; padding: 16px; }}
  #map {{ height: 640px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
  .timeline {{ background: #fff; border-radius: 12px; padding: 16px; max-height: 640px; overflow-y: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
  .timeline h2 {{ margin: 0 0 12px; font-size: 16px; }}
  .timeline-item {{ padding: 10px 0; border-bottom: 1px solid #e2e8f0; }}
  .timeline-item:last-child {{ border-bottom: none; }}
  .timeline-year {{ color: #0369a1; font-weight: 600; font-size: 13px; }}
  .timeline-place {{ color: #7c3aed; margin-left: 8px; font-size: 12px; }}
  .timeline-event {{ margin-top: 4px; font-size: 14px; line-height: 1.55; }}
  footer {{ padding: 12px 24px; font-size: 12px; color: #64748b; }}
  footer a {{ color: #0369a1; }}
  .leaflet-control-layers {{ font-size: 12px; }}
</style>
</head>
<body>
<header>
  <h1>{name}</h1>
  <p>{short_review}</p>
</header>
<main>
  <div id="map"></div>
  <aside class="timeline">
    <h2>足迹时间线</h2>
    {timeline_html}
  </aside>
</main>
<footer>
  默认底图 &copy; 高德地图公开瓦片；备用底图 &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · 坐标表保留 WGS84，国内高德底图显示点位使用 GCJ-02 · 由 1+5 Agent（Supervisor + Search / Map / Editor / Critic / Deliver）协同生成
</footer>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const COORDS = {coords_json};
  const map = L.map('map');
  const amap = L.tileLayer('https://webrd0{{s}}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={{x}}&y={{y}}&z={{z}}', {{
    subdomains: ['1', '2', '3', '4'],
    maxZoom: 18,
    attribution: '© 高德地图'
  }}).addTo(map);
  const osm = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 18,
    attribution: '© OpenStreetMap contributors'
  }});
  L.control.layers({{ '高德底图（默认）': amap, 'OpenStreetMap 备用': osm }}).addTo(map);
  if (COORDS.length > 0) {{
    const bounds = [];
    COORDS.forEach((p, idx) => {{
      const marker = L.marker([p.mapLat, p.mapLon]).addTo(map);
      marker.bindPopup(`<b>${{idx + 1}}. ${{p.name}}</b><br>WGS84: ${{p.lat.toFixed(4)}}, ${{p.lon.toFixed(4)}}`);
      bounds.push([p.mapLat, p.mapLon]);
    }});
    if (COORDS.length > 1) {{
      L.polyline(bounds, {{ color: '#0369a1', weight: 2, opacity: 0.6 }}).addTo(map);
    }}
    map.fitBounds(bounds, {{ padding: [40, 40] }});
  }} else {{
    map.setView([35, 105], 4);
  }}
</script>
</body>
</html>
"""


def render(md_path: Path, out_path: Path, name: str | None = None) -> None:
    md = md_path.read_text(encoding="utf-8")
    person_name = name or md_path.stem
    short_review = _parse_short_review(md, person_name)
    timeline = _parse_timeline(md)
    coords = _parse_coords(md)

    timeline_items = []
    for year, place, event in timeline:
        timeline_items.append(
            f'<div class="timeline-item"><span class="timeline-year">{html.escape(year)}</span>'
            f'<span class="timeline-place">@ {html.escape(place)}</span>'
            f'<div class="timeline-event">{html.escape(event)}</div></div>'
        )
    if not timeline_items:
        timeline_items.append('<div class="timeline-item">（无时间线数据）</div>')

    map_coords = []
    for n, lat, lon in coords:
        map_lat, map_lon = wgs84_to_gcj02(lat, lon)
        map_coords.append({"name": n, "lat": lat, "lon": lon, "mapLat": map_lat, "mapLon": map_lon})
    coords_json = json.dumps(map_coords, ensure_ascii=False)

    rendered = HTML_TEMPLATE.format(
        name=html.escape(person_name),
        short_review=html.escape(short_review),
        timeline_html="".join(timeline_items),
        coords_json=coords_json,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="将 6-Agent 产出的 md 渲染为 Leaflet 故事地图 HTML（默认高德底图，OSM 备用）")
    parser.add_argument("--md", required=True, type=Path, help="输入 Markdown 路径")
    parser.add_argument("--out", type=Path, default=None, help="输出 HTML 路径")
    parser.add_argument("--name", default=None, help="人物姓名（默认取 md 文件名）")
    args = parser.parse_args(argv)

    if not args.md.exists():
        print(f"[fatal] 找不到 md 文件：{args.md}", file=sys.stderr)
        return 2
    out_path = args.out or args.md.with_suffix(".osm.html")
    render(args.md, out_path, args.name)
    print(f"[done] osm html -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
