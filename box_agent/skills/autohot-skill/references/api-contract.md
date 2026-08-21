# AutoHOT API 契约

## 1. 基础配置

- 默认线上 Base URL：`https://autohot.coze.site`
- 环境变量优先级：`AUTOHOT_BASE_URL` > `COZE_PROJECT_DOMAIN_DEFAULT` > 默认线上 Base URL。
- 所有接口路径以 `/api` 开头。
- 当前公开页面展示的 API 返回统一 JSON 信封：

```json
{
  "success": true,
  "data": {}
}
```

执行时不得仅凭 HTTP 200 判定成功；必须同时检查 `success` 字段和 `data` 内容。

## 2. 接口清单

| 任务 | 方法 | 路径 | 关键参数 | 用途 |
|---|---|---|---|---|
| 每日精选 | GET | `/api/featured` | `date`, `category` | 获取每日精选汽车热点事件 |
| 全量资讯流 | GET | `/api/feed` | `sort`, `search`, `category`, `source_tier`, `car_model`, `limit`, `offset` | 获取全部汽车资讯与分页结果 |
| 每日行业日报 | GET | `/api/daily` | `date`, `recent` | 获取指定日期或最近日报 |
| 事件详情 | GET | `/api/events/:id` | `id` | 获取单个事件详情 |
| 品牌事件 | GET | `/api/brands` | `brand`, `limit`, `offset` | 获取品牌列表或指定品牌近 7 天事件 |
| 赛道事件 | GET | `/api/tracks` | `category`, `sort`, `limit`, `offset` | 获取赛道统计或指定赛道事件 |
| 销售晨会简报 | GET | `/api/reports/sales-briefing` | `date` | 生成销售团队每日晨会简报 |
| 管理层周报 | GET | `/api/reports/weekly` | `start_date`, `end_date` | 生成管理层周报 |
| 分析师简报 | GET | `/api/briefing` | `date` | 获取分析师简报（核心信号/趋势洞察/关注事项） |

## 3. 参数规则

- 日期使用 `YYYY-MM-DD`。
- `category` 使用中文分类名；若用户输入模糊，应优先从站点返回的分类/赛道中匹配，无法匹配时说明限制。
- `brand` 使用中文品牌名；品牌别名需要在输出中注明映射关系。
- `sort` 仅允许 `score` 或 `time`。
- `limit`、`offset` 用于分页；默认 `limit` 不应过大，避免一次性拉取过量数据。
- `start_date` 和 `end_date` 用于周报；如果用户只说“本周”，按自然周或业务周推算，并在输出中说明。

## 4. 调用示例

```bash
curl "https://autohot.coze.site/api/daily?recent=true"
curl "https://autohot.coze.site/api/featured?date=2026-06-19"
curl "https://autohot.coze.site/api/feed?sort=score&limit=20&offset=0"
curl "https://autohot.coze.site/api/brands?brand=比亚迪&limit=20"
curl "https://autohot.coze.site/api/reports/weekly?start_date=2026-06-15&end_date=2026-06-21"
curl "https://autohot.coze.site/api/briefing?date=2026-06-26"
```

## 5. 成功判定

一次 API 调用只有同时满足以下条件，才可视为可用于正式输出：

1. HTTP 状态码为 2xx；
2. 响应可以解析为 JSON；
3. `success === true`；
4. `data` 存在；
5. 若用户要求实时日报，返回数据的日期或更新时间与请求时间范围一致。

## 6. 真实联调返回结构

截至本技能包联调时，主要端点的真实返回结构如下。后续若线上接口升级，应以重新联调结果为准更新本节。

| 端点 | 实测 data 类型 | 主要字段 |
|---|---|---|
| `/api/featured` | object | `events`, `stats`, `isFallback` |
| `/api/feed` | list | `id`, `article_id`, `summary`, `category`, `entities`, `scores`, `final_score`, `is_featured`, `recommend_reasons`, `event_cluster_id`, `processed_at`, `title_zh` |
| `/api/daily?recent=true` | list | `id`, `report_date`, `title`, `featured_count`, `total_count` |
| `/api/daily` / `/api/daily?date=YYYY-MM-DD` | object | `id`, `report_date`, `title`, `summary`, `content_json`, `content_md`, `featured_count`, `total_count`, `brand_count`, `event_count`, `created_at` |
| `/api/brands` | list | `id`, `name`, `group_name`, `english_name`, `logo_url`, `is_active`, `created_at`, `event_count` |
| `/api/brands?brand=...` | object | `events`, `total` |
| `/api/tracks` | list | `category`, `count`, `topEvents` |
| `/api/tracks?category=...` | object | `events`, `total` |
| `/api/reports/sales-briefing` | object | `date`, `generated_at`, `headline`, `key_points`, `price_actions`, `new_launches`, `policy_updates`, `competitor_moves`, `suggested_talking_points` |
| `/api/reports/weekly` | object | `date`, `generated_at`, `summary`, `sections`, `stats` |
| `/api/briefing` | object | `report_date`, `one_liner`, `core_signals`, `trend_insights`, `watch_items`, `data_snapshot`, `event_map` |
| `/api/events/:id` | object | `id`, `title`, `summary`, `category`, `brands`, `scores`, `final_score`, `is_featured`, `recommend_reasons`, `article_count`, `first_seen_at`, `last_seen_at` |

### `/api/briefing` 返回结构详解

```json
{
  "success": true,
  "data": {
    "report_date": "2026-07-08",
    "one_liner": "一句话概要，概括当日市场核心动态",
    "core_signals": [
      {
        "title": "核心信号标题",
        "analysis": "详细分析内容",
        "event_ids": [1234, 5678],
        "impact": "对行业/品牌的影响说明"
      }
    ],
    "trend_insights": [
      {
        "title": "趋势洞察标题",
        "strength": "strong|medium|weak",
        "brands": ["品牌1", "品牌2"],
        "analysis": "趋势分析内容"
      }
    ],
    "watch_items": [
      {
        "title": "关注事项标题",
        "context": "背景说明",
        "date_context": "时间背景"
      }
    ],
    "data_snapshot": {
      "total_events": 60,
      "featured_events": 15,
      "top_brands": ["品牌1", "品牌2"],
      "track_distribution": {
        "电动化": 10,
        "智能化": 15,
        "市场": 20
      }
    }
  },
  "event_map": {
    "1234": "事件标题1",
    "5678": "事件标题2"
  }
}
```

**字段说明**：
- `one_liner`: 一句话概括当日市场核心动态
- `core_signals`: 核心信号列表，每个信号关联具体事件（event_ids）
- `trend_insights`: 趋势洞察列表，包含强度标签（strong/medium/weak）和关联品牌
- `watch_items`: 需要关注的事项列表
- `data_snapshot`: 数据快照，包含事件统计、热门品牌、赛道分布
- `event_map`: 事件ID到标题的映射，用于展示核心信号关联的事件标题

## 7. 空数据与异常表现

- 空数组、空对象或 `success=false` 不等于“事实不存在”。
- 输出应写为“本次未检到符合条件的数据”。
- 应建议扩大时间范围、放宽关键词、切换品牌别名或改用赛道查询。
- 不得自行补写新闻、来源或影响判断。
- 真实联调发现：不存在的事件详情 `/api/events/999999999` 返回 HTTP 500，JSON 为 `success=false`，错误信息为 `Failed to fetch event`。调用方必须把它视为“事件不可用/不存在或后端查询失败”，不得重试后仍失败时编造详情。
- `/api/featured` 可能返回 `isFallback` 字段；若为 `true`，输出必须说明本次使用了后端 fallback 数据，不应表述为完全命中的实时精选结果。

## 8. 线上配置检查

执行实时线上任务前，先确认：

- 使用的 Base URL；
- 能否访问目标接口；
- 返回是否为 AutoHOT JSON 信封；
- 数据时间范围是否满足用户需求。

若缺少线上配置或接口不可达，必须按 `references/error-handling.md` 降级，不得冒充实时线上日报。
