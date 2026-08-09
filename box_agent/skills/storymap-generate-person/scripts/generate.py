#!/usr/bin/env python3
"""storymap-generate-person · 1+5 Agent 人物档案生成 CLI（skill 版）。

关键差异（对比 artifacts/agent_submission/run_pipeline.py）：
    * 支持 --provider {auto|amap|osm}，OSM 时禁用高德读取
    * 支持 --basemap {osm|amap|geovis}，写入 render 提示
    * 支持 --render：生成 md 后立即调用项目内 profile.renderer 渲染 HTML
    * 无 --render 时纯 md 产出（用户可自行接 build 流程）

用法示例：
    python generate.py --name 张仲景                              # 默认 OSM
    AMAP_KEY=xxx python generate.py --name 张仲景                  # 高德
    python generate.py --name 张仲景 --provider osm --render      # 强制 OSM + 立即渲染
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 定位到项目根：本脚本位于 <repo>/.trae/skills/storymap-generate-person/scripts/generate.py
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT))


def _resolve_provider(cli_arg: str) -> str:
    """决定实际使用的地理编码后端。"""
    cli_arg = (cli_arg or "auto").lower()
    if cli_arg in ("amap", "gaode", "高德"):
        return "amap"
    if cli_arg in ("osm", "openstreetmap", "nominatim"):
        return "osm"
    # auto: 存在 AMAP 相关 key 则走高德，否则 OSM
    amap_env_names = (
        "AMAP_KEY", "AMAP_WEBSERVICE_KEY", "AMAP_WEB_SERVICE_KEY",
        "AMAP_REST_KEY", "locaion_api", "location_api", "LOCATION_API",
    )
    for key in amap_env_names:
        if (os.environ.get(key) or "").strip():
            return "amap"
    return "osm"


def _apply_osm_provider_env() -> None:
    """让 map 模块看不到任何 AMAP_KEY，从而自动降级到 Nominatim + Wikidata。"""
    for key in (
        "AMAP_KEY", "AMAP_WEBSERVICE_KEY", "AMAP_WEB_SERVICE_KEY",
        "AMAP_REST_KEY", "locaion_api", "location_api", "LOCATION_API",
    ):
        if key in os.environ:
            del os.environ[key]
    # Nominatim 官方使用政策要求 User-Agent
    os.environ.setdefault(
        "MAP_STORY_NOMINATIM_USER_AGENT",
        "storymap.cn/1.0 (contact@storymap.cn)",
    )


def _resolve_basemap(cli_arg: str | None, provider: str) -> str:
    if cli_arg:
        return cli_arg.lower()
    if provider == "amap":
        return "amap" if not (os.environ.get("GEOVIS_TOKEN") or "").strip() else "geovis"
    return "osm"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate-person",
        description="1+5 Agent 协同生成历史人物 Markdown 档案（默认 OSM 底图）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--name", required=True, help="人物姓名（简体中文）")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出 md 路径；默认写到 storymap/examples/story/<name>.md",
    )
    parser.add_argument(
        "--provider",
        choices=("auto", "amap", "osm"),
        default="auto",
        help="地理编码后端：auto 自动选择、amap 高德、osm OpenStreetMap",
    )
    parser.add_argument(
        "--basemap",
        choices=("osm", "amap", "geovis"),
        default=None,
        help="页面底图（默认跟随 provider）",
    )
    parser.add_argument("--max-revisions", type=int, default=3)
    parser.add_argument("--render", action="store_true", help="生成后立即渲染 HTML")
    parser.add_argument("--dump-state", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不真正调用 LLM")
    return parser


def _emit_plan(args, provider: str, basemap: str, out_path: Path) -> None:
    print(f"[plan] name        = {args.name}")
    print(f"[plan] provider    = {provider}")
    print(f"[plan] basemap     = {basemap}")
    print(f"[plan] out_md      = {out_path}")
    print(f"[plan] max_revs    = {args.max_revisions}")
    print(f"[plan] render_html = {args.render}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    provider = _resolve_provider(args.provider)
    if provider == "osm":
        _apply_osm_provider_env()
    basemap = _resolve_basemap(args.basemap, provider)

    out_path = args.out or (REPO_ROOT / "storymap" / "examples" / "story" / f"{args.name}.md")
    out_path = Path(out_path)

    _emit_plan(args, provider, basemap, out_path)

    if args.dry_run:
        print("[dry-run] 未真正执行，退出")
        return 0

    if not os.environ.get("LLM_API_KEY") and not os.environ.get("MINIMAX_API_KEY"):
        print(
            "[fatal] 未检测到 LLM_API_KEY / MINIMAX_API_KEY 环境变量。",
            file=sys.stderr,
        )
        return 2

    # 延迟 import，避免 dry-run 时也拉起整个项目
    from storymap.script.agent.llm_client import StoryAgentLLM
    from storymap.script.runtime.legacy_agent.graph import generate_markdown_with_agents

    llm = StoryAgentLLM()
    print(f"[run] invoking 6-Agent pipeline (llm_model={getattr(llm, 'model_id', '?')})")
    result = generate_markdown_with_agents(
        llm=llm,
        person=args.name,
        max_revisions=args.max_revisions,
        allow_unknown=True,
    )

    markdown = str(result.get("markdown") or "").strip()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown + "\n", encoding="utf-8")
    print(f"[done] md    -> {out_path}  ({len(markdown)} chars)")

    if args.dump_state:
        state_slim = {k: v for k, v in result.items() if k != "markdown"}
        args.dump_state.write_text(
            json.dumps(state_slim, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"[done] state -> {args.dump_state}")

    ok = bool(result.get("ok"))
    print(f"[quality] ok={ok}  issues={len(result.get('issues') or [])}")

    if args.render:
        html_dir = REPO_ROOT / "artifacts" / "story_map"
        html_dir.mkdir(parents=True, exist_ok=True)
        html_path = html_dir / f"{args.name}.html"
        if basemap == "osm":
            # OSM 走 skill 内置的 Leaflet stub，避免依赖主仓 GeoVis/AMap 前端模板
            sys.path.insert(0, str(SCRIPT_DIR))
            from render_osm import render as render_osm_html  # type: ignore

            render_osm_html(out_path, html_path, args.name)
            print(f"[done] html  -> {html_path}  (OSM · Leaflet)")
        else:
            try:
                os.environ["MAP_STORY_DEFAULT_BASEMAP"] = basemap
                from storymap.script.profile.renderer import render_amap_html  # type: ignore
            except ImportError as exc:
                print(f"[warn] 渲染模块不可用，跳过 HTML 生成：{exc}", file=sys.stderr)
            else:
                html_body, _meta = render_amap_html(str(out_path), str(html_path))
                if html_body and not html_path.exists():
                    html_path.write_text(html_body, encoding="utf-8")
                print(f"[done] html  -> {html_path}  ({basemap})")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
