#!/usr/bin/env python3
"""Match user tasks to local skills and suggest SkillHub fallback.

This script is intentionally lightweight. It supports the skill's user-facing
reasoning but does not replace final human/agent judgment.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
SCAN_SCRIPT = ROOT / "scan_skills.py"

INTENT_KEYWORDS = {
    "写作内容": ["写", "文章", "公众号", "稿", "润色", "改写", "标题"],
    "数据分析": ["数据", "表格", "excel", "分析", "可视化", "统计"],
    "技能创建": ["技能", "skill", "skillhub", "打包", "优化技能", "创建技能", "SKILL.md", "技能包", "上传", "校验", "front matter"],
    "知识管理": ["知识库", "笔记", "资料", "收藏", "搜索知识"],
    "地图出行": ["地图", "路线", "天气", "地点", "行程", "导航"],
    "专家顾问": ["专家", "评估", "策略", "服务设计", "咨询", "复盘"],
    "通用办公": ["周报", "日报", "汇报", "文档", "ppt", "word", "合同"],
}

STAGE_HINTS = [
    ("澄清目标", ["需求", "目标", "计划", "拆解"]),
    ("收集资料", ["搜索", "调研", "知识库", "资料", "网页"]),
    ("分析判断", ["分析", "评估", "对比", "审计", "诊断"]),
    ("生成交付", ["写", "生成", "制作", "报告", "文章", "文档"]),
    ("校验发布", ["校验", "打包", "发布", "安装", "上传", "测试"]),
]

SKILLHUB_SEARCH_TERMS = {
    "写作内容": ["公众号 写作", "长文 改写", "内容创作"],
    "数据分析": ["Excel 数据分析", "可视化 报告", "数据清洗"],
    "技能创建": ["SkillHub 技能创建", "SKILL.md 优化", "技能包 打包 校验"],
    "知识管理": ["知识库 笔记", "资料管理", "网页收藏"],
    "地图出行": ["地图 路线 天气", "旅行攻略", "地点搜索"],
    "专家顾问": ["专家团 评估", "服务设计", "策略咨询"],
    "通用办公": ["周报 文档", "PPT 生成", "合同审查"],
}


def run_scan() -> List[Dict[str, Any]]:
    proc = subprocess.run([sys.executable, str(SCAN_SCRIPT), "--json"], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "scan_skills.py failed")
    return json.loads(proc.stdout or "[]")


def tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"\s+|[,，。；;:：/\\-]+", text.lower()) if t]


def infer_categories(task: str) -> List[str]:
    cats = []
    lower = task.lower()
    for cat, kws in INTENT_KEYWORDS.items():
        if any(k.lower() in lower for k in kws):
            cats.append(cat)
    return cats or ["通用办公"]


def score_skill(task: str, skill: Dict[str, Any], categories: List[str]) -> int:
    hay = " ".join(str(skill.get(k, "")) for k in ["english_name", "chinese_name", "description_zh", "category"]).lower()
    task_lower = task.lower()
    score = 0
    for token in tokenize(task):
        if token and token in hay:
            score += 12
    if "技能创建" in categories and any(k in task_lower for k in ["优化", "打包", "上传", "校验", "skillhub", "技能包"]):
        exact_name = str(skill.get("english_name", "")).lower()
        if any(k in exact_name for k in ["skill-creator", "skillhub-standard", "office-raccoon-skill-creator"]):
            score += 80
        elif any(k in hay for k in ["创建、优化、审计和打包", "yaml 修复", "上架资产", "trace 评测", "交付包优化"]):
            score += 55
        elif any(k in hay for k in ["作者", "写作", "仿写", "服务设计", "专家团", "客户旅程"]):
            score -= 45
    if skill.get("category") in categories:
        score += 35
    if skill.get("health") == "normal":
        score += 8
    if skill.get("name_confidence") == "高":
        score += 4
    elif skill.get("name_confidence") == "低":
        score -= 4
    return max(score, 0)


def workflow(task: str, skills: List[Dict[str, Any]], matches: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    lower = task.lower()
    stages = [name for name, kws in STAGE_HINTS if any(k.lower() in lower for k in kws)]
    if len(stages) < 2 and ("并" in task or "然后" in task or "最后" in task or len(task) > 28):
        stages = ["澄清目标", "分析判断", "生成交付", "校验发布"]
    if not stages:
        return []
    top = matches[:3]
    rows = []
    for i, stage in enumerate(stages[:6], 1):
        primary = top[min(i - 1, len(top) - 1)]["english_name"] if top else "待从 SkillHub 补齐"
        rows.append({"step": str(i), "stage": stage, "primary_skill": primary, "output": f"完成{stage}的阶段结果", "switch_condition": "阶段输出可用后进入下一步；若匹配度不足则先补齐技能。"})
    return rows


def skillhub_fallback(categories: List[str]) -> Dict[str, Any]:
    terms = []
    for cat in categories:
        terms.extend(SKILLHUB_SEARCH_TERMS.get(cat, []))
    if not terms:
        terms = ["办公 自动化", "AI 技能", "任务助手"]
    return {
        "message": "本地没有找到足够高匹配的技能，建议去 SkillHub 补齐。安装或覆盖前需要用户确认。",
        "search_terms": list(dict.fromkeys(terms))[:6],
        "filter_rules": ["优先看 description 是否写清输入输出", "优先选择有 FAQ/边界说明/示例的技能", "安装前检查 ZIP 根目录是否包含 SKILL.md"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend local skills for a task")
    parser.add_argument("task", help="User task text")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    categories = infer_categories(args.task)
    skills = run_scan()
    matches = []
    for skill in skills:
        s = score_skill(args.task, skill, categories)
        if s > 0:
            matches.append({**skill, "match_score": min(s, 100), "match_reason": f"任务类别可能属于 {', '.join(categories)}，与该技能的说明/类别存在匹配。"})
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    high = [m for m in matches if m["match_score"] >= 40][:3]
    result = {
        "task": args.task,
        "inferred_categories": categories,
        "recommendations": high,
        "workflow": workflow(args.task, skills, high),
        "skillhub_fallback": skillhub_fallback(categories) if not high or high[0]["match_score"] < 55 else None,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"任务类别：{', '.join(categories)}")
        if high:
            print("推荐技能：")
            for m in high:
                print(f"- {m['english_name']} / {m['chinese_name']}：{m['match_score']} 分。{m['match_reason']}")
        if result["workflow"]:
            print("建议流程：")
            for row in result["workflow"]:
                print(f"{row['step']}. {row['stage']} → {row['primary_skill']} → {row['output']}")
        if result["skillhub_fallback"]:
            fb = result["skillhub_fallback"]
            print(fb["message"])
            print("可搜关键词：" + "；".join(fb["search_terms"]))


if __name__ == "__main__":
    main()
