---
name: autohot-skill
description: "汽车行业每日情报 Skill：基于 AutoHOT 公开接口查询汽车热点、日报、品牌动态、赛道趋势，并生成销售晨会简报、管理层周报和事件影响分析。"
---

# AutoHOT 汽车行业每日情报 Skill

## 北极星目标

帮助用户基于 AutoHOT 汽车行业情报能力，快速获得**可追溯、可审计、可直接用于业务沟通**的汽车行业动态、日报、品牌追踪、赛道趋势、销售晨会简报、管理层周报和事件影响分析。

本 Skill 的成功标准不是“看起来像新闻摘要”，而是：

- 事实有来源；
- 时间范围清楚；
- 是否实时线上数据说清楚；
- 事实、推断、建议分开；
- 出现接口、权限、无数据问题时不虚构、不冒充；
- 输出能被销售、运营、管理层直接使用。

## 线上事实依据

AutoHOT 开发者页显示的默认线上服务：

- Base URL：`https://autohot.coze.site`
- API 路径前缀：`/api/...`
- 响应信封：`{ success: boolean, data: any }`
- 高频端点：
  - `GET /api/featured`
  - `GET /api/feed`
  - `GET /api/daily`
  - `GET /api/events/:id`
  - `GET /api/brands`
  - `GET /api/tracks`
  - `GET /api/reports/sales-briefing`
  - `GET /api/reports/weekly`
  - `GET /api/briefing`

详见：`references/api-contract.md`。

## 适用触发

当用户请求涉及以下任一场景时，优先使用本 Skill：

- AutoHOT、汽车行业日报、汽车热点、汽车资讯、汽车行业情报；
- 车企、品牌、车型、供应链、智能驾驶、新能源、补能、出海、价格战等动态；
- 生成汽车行业销售晨会简报、管理层周报、事件影响分析；
- 查询某品牌、某赛道、某时间范围内的汽车行业事件；
- 需要把汽车新闻转化为销售话术、客户沟通点、运营动作或管理层关注事项。

## 不适用边界

以下情况不要直接使用本 Skill，除非用户明确要求基于 AutoHOT 或汽车行业情报：

- 非汽车行业新闻汇总；
- 通用销售简报、通用管理周报、普通会议纪要；
- 车辆维修保养、购车导购、车辆参数深度对比；
- 股票买卖建议、目标价判断、证券投资建议；
- 法律责任、监管合规最终意见；
- 复刻受版权保护新闻全文、绕过登录或付费墙。

遇到投资、法律、版权或绕过限制类请求，应拒绝违规部分，并提供合规替代：只做行业事实整理、公开信息摘要、风险提示或待专业人士确认的事项列表。

## 渐进式加载规则

首次调用只读取本入口。识别任务类型后，再按需加载对应模块：

| 用户任务 | 必读模块 | 推荐模板 |
|---|---|---|
| 今日日报 / 指定日期日报 | `references/api-contract.md`、`references/data-quality-rules.md` | `templates/daily-brief.md` |
| 分析师简报 / 核心观点 / 趋势洞察 | `references/api-contract.md`、`references/data-quality-rules.md` | `templates/daily-brief.md` |
| 销售晨会简报 | `references/api-contract.md`、`references/delivery-contract.md` | `templates/sales-morning-brief.md` |
| 管理层周报 | `references/api-contract.md`、`references/data-quality-rules.md` | `templates/management-weekly-report.md` |
| 品牌/公司动态 | `references/api-contract.md`、`references/data-quality-rules.md` | `templates/daily-brief.md` 或自定义品牌追踪结构 |
| 赛道趋势 | `references/api-contract.md`、`references/data-quality-rules.md` | `templates/management-weekly-report.md` |
| 单事件影响分析 | `references/api-contract.md`、`references/data-quality-rules.md` | `templates/event-impact-analysis.md` |
| API 失败 / 无数据 / 配置缺失 | `references/error-handling.md` | `examples/no-data-example.md`、`examples/api-config-missing-example.md` |
| 用户要求文件交付 | `references/delivery-contract.md` | 按任务选择模板 |

## 默认执行原则

1. **优先线上 AutoHOT 接口**：默认 baseUrl 为 `https://autohot.coze.site`；如果运行环境另有 `AUTOHOT_BASE_URL` 或 `COZE_PROJECT_DOMAIN_DEFAULT`，以显式配置为准。
2. **先检查实时性**：输出前必须标注查询时间、数据时间范围、数据更新时间或接口返回时间；如果无法确认实时性，必须说明。
3. **缺省时间规则**：
   - “今天”：使用当天日期；
   - “最近”：默认最近 7 天；
   - “周报”：默认最近 7 天，或按用户指定起止日期；
   - 用户指定日期优先于默认值。
4. **参数缺失处理**：
   - 缺少非关键参数时使用默认值并说明；
   - 缺少关键参数且无法合理推断时追问；
   - 品牌、分类、事件 ID 存在歧义时列出候选或说明采用的解释。
5. **不虚构**：接口无数据、失败或未配置时，不得编造新闻、来源、实时性或文件路径。
6. **业务转化**：面向销售、运营、管理层的输出，必须把事实转化为可执行关注点，但要把事实与推断分开。

## 任务路由

| 意图 | 推荐接口 | 关键参数 | 默认值 |
|---|---|---|---|
| 每日精选热点 | `GET /api/featured` | `date`、`category` | 今天、全部分类 |
| 全量资讯流 | `GET /api/feed` | `sort`、`search`、`category`、`limit`、`offset` | `score`、20 条 |
| 每日行业日报 | `GET /api/daily` | `date` 或 `recent=true` | 今天 |
| 单事件详情 | `GET /api/events/:id` | `id` | 必填 |
| 品牌动态 | `GET /api/brands` | `brand`、`limit`、`offset` | 最近 7 天、20 条 |
| 赛道趋势 | `GET /api/tracks` | `category`、`sort`、`limit` | 全部赛道或指定分类 |
| 销售晨会简报 | `GET /api/reports/sales-briefing` | `date` | 今天 |
| 管理层周报 | `GET /api/reports/weekly` | `start_date`、`end_date` | 最近 7 天 |
| 分析师简报 | `GET /api/briefing` | `date` | 今天 |

## 输出质量门禁

交付前必须自检：

- 是否说明数据来源、查询时间、时间范围；
- 是否说明是否来自实时线上 AutoHOT；
- 是否为关键事实提供来源或接口依据；
- 是否区分事实、分析推断、业务建议；
- 是否说明数据限制、接口失败、空数据或配置缺失；
- 是否避免把“未检到”写成“事实不存在”；
- 若生成文件，是否真实写入、可打开、命名规范；
- 多文件交付时是否打包并只提供 ZIP。

## 最终汇报要求

最终回复必须包含：

- 任务是否完成；
- 使用的数据来源或接口；
- 覆盖时间范围；
- 是否为实时线上 AutoHOT 数据；
- 已知限制；
- 若有文件，提供真实路径链接；
- 推荐下一步。

## SDK 类型定义参考

以下为 TypeScript 类型定义，供集成开发时参考：

```typescript
// ── 基础类型 ──

export type SortMode = 'score' | 'time';

export interface AutoHotConfig {
  baseUrl?: string;
  token?: string;
  timeoutMs?: number;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface FeedQuery {
  sort?: SortMode;
  search?: string;
  category?: string;
  source_tier?: 'official' | 'media' | 'kol' | string;
  car_model?: string;
  limit?: number;
  offset?: number;
}

export interface DateQuery {
  date?: string;
  recent?: boolean;
}

export interface WeeklyQuery {
  start_date: string;
  end_date: string;
}

export interface ListQuery {
  brand?: string;
  category?: string;
  sort?: SortMode;
  limit?: number;
  offset?: number;
}

// ── 事件与报告 ──

export interface AutoHotEvent {
  id?: number | string;
  title?: string;
  title_zh?: string;
  summary?: string;
  category?: string;
  brands?: string[];
  final_score?: number;
  is_featured?: boolean;
  recommend_reasons?: string[];
  article_count?: number;
  source_tier?: string;
  url?: string;
  published_at?: string;
  first_seen_at?: string;
  last_seen_at?: string;
  [key: string]: unknown;
}

export interface AutoHotReport {
  id?: number | string;
  title?: string;
  report_date?: string;
  content_md?: string;
  featured_count?: number;
  total_count?: number;
  [key: string]: unknown;
}

// ── 分析师简报 ──

export interface CoreSignal {
  title: string;
  analysis: string;
  impact: string;
  event_ids: number[];
}

export interface TrendInsight {
  title: string;
  analysis: string;
  brands: string[];
  strength: 'strong' | 'medium' | 'weak';
}

export interface WatchItem {
  title: string;
  context: string;
  date_context?: string;
}

export interface DataSnapshot {
  total: number;
  featured: number;
  track_distribution: Record<string, number>;
  top_brands: string[];
}

export interface AnalystBriefing {
  id: number;
  report_date: string;
  one_liner: string;
  core_signals: CoreSignal[];
  trend_insights: TrendInsight[];
  watch_items: WatchItem[];
  data_snapshot: DataSnapshot;
  created_at: string;
}
```

## HTTP 客户端参考

以下为 TypeScript HTTP 客户端实现参考，供集成开发时使用。实际调用可直接使用 `curl` 或任意 HTTP 库。

```typescript
const DEFAULT_BASE_URL = 'https://autohot.coze.site';

function normalizeBaseUrl(baseUrl?: string): string {
  const value = baseUrl
    || process.env.AUTOHOT_BASE_URL
    || process.env.COZE_PROJECT_DOMAIN_DEFAULT
    || DEFAULT_BASE_URL;
  return value.replace(/\/$/, '');
}

class AutoHotClient {
  private readonly baseUrl: string;
  private readonly token?: string;
  private readonly timeoutMs: number;

  constructor(config: AutoHotConfig = {}) {
    this.baseUrl = normalizeBaseUrl(config.baseUrl);
    this.token = config.token || process.env.AUTOHOT_API_TOKEN;
    this.timeoutMs = config.timeoutMs ?? 15000;
  }

  async request<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';

    try {
      const response = await fetch(`${this.baseUrl}${path}${query}`, {
        method: 'GET', headers, signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const envelope = (await response.json()) as ApiEnvelope<T>;
      if (!envelope.success) throw new Error(envelope.error || 'API returned success=false');
      return envelope.data as T;
    } finally {
      clearTimeout(timer);
    }
  }

  // 便捷方法
  featured(params?: DateQuery & { category?: string }) { return this.request('/api/featured', params); }
  feed(params?: FeedQuery) { return this.request('/api/feed', params); }
  daily(params?: DateQuery) { return this.request('/api/daily', params); }
  event(id: number | string) { return this.request(`/api/events/${id}`); }
  brands(params?: ListQuery) { return this.request('/api/brands', params); }
  tracks(params?: ListQuery) { return this.request('/api/tracks', params); }
  salesBriefing(params?: DateQuery) { return this.request('/api/reports/sales-briefing', params); }
  weekly(params: WeeklyQuery) { return this.request('/api/reports/weekly', params); }
  briefing(params?: DateQuery) { return this.request('/api/briefing', params); }
}
```

## 任务路由参考

根据用户输入自动识别任务类型并路由到对应接口：

```typescript
type AutoHotTaskType =
  | 'daily-brief' | 'analyst-briefing' | 'sales-morning-brief'
  | 'management-weekly-report' | 'company-tracking'
  | 'track-analysis' | 'event-impact-analysis' | 'feed-search';

// 路由规则（按优先级排列）：
// 1. 晨会/销售简报 → sales-morning-brief → /api/reports/sales-briefing
// 2. 周报/管理层 → management-weekly-report → /api/reports/weekly
// 3. 日报/今日 → daily-brief → /api/daily
// 4. 分析师/简报/洞察/信号 → analyst-briefing → /api/briefing
// 5. 事件/影响/解读 → event-impact-analysis → /api/events/:id
// 6. 品牌/车企/比亚迪/特斯拉 → company-tracking → /api/brands
// 7. 赛道/智驾/新能源/补能 → track-analysis → /api/tracks
// 8. 默认 → feed-search → /api/feed
```

## 参考模块

- API 契约：`references/api-contract.md`
- 异常处理：`references/error-handling.md`
- 交付契约：`references/delivery-contract.md`
- 数据质量规则：`references/data-quality-rules.md`
- 输出模板：`templates/`
- 示例样例：`examples/`
