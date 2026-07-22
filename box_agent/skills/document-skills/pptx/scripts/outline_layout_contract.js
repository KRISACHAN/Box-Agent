"use strict";

const CHINESE_COUNTS = Object.freeze({
  一: 1,
  二: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
  十: 10,
});

const QUADRANT_RE = /(?:四象限|象限图|quadrant)/i;
const MATRIX_RE = /(?:风险\s*[\/+与、]?依赖)?矩阵|matrix|(?:结构化)?表格|\btable\b/i;
const BAR_CHART_RE = /(?:柱状图|条形图|排名图|bar\s*chart|column\s*chart)/i;
const DATA_CHART_RE = /(?:折线图|面积图|饼图|环形图|雷达图|数据图表|line\s*chart|area\s*chart|pie\s*chart|donut\s*chart|radar\s*chart)/i;
const ARCHITECTURE_RE = /(?:分层架构|技术架构|系统架构|解决方案架构|架构图|architecture(?:\s*(?:diagram|layered))?)/i;
const INTEGRATION_RE = /(?:系统集成|集成架构|数据流(?:设计|图)?|接口关系|integration(?:\s*(?:diagram|map))?|data\s*flow)/i;
const DATA_PIPELINE_RE = /(?:数据管道|数据流水线|处理管道|ETL|ELT|data\s*pipeline|processing\s*pipeline)/i;
const DASHBOARD_RE = /(?:数据看板|管理看板|管理驾驶舱|运营驾驶舱|dashboard(?:\s*overview)?)/i;
const KPI_RE = /(?:KPI|指标卡|metrics?\s*(?:grid|board))/i;
const GANTT_RE = /(?:甘特(?:图|计划)?|gantt(?:\s*(?:chart|plan|schedule))?)/i;
const TIMELINE_RE = /(?:时间轴|路线图|里程碑|节点串联|timeline|roadmap)/i;
const PROCESS_RE = /(?:三段式|四段式|能力路径|演进路径|流程路径|process\s*flow|journey)/i;
const COMPARISON_RE = /(?:双栏对比|前后对比|方案对比|two[- ]column\s*comparison|before\s*(?:and|\/)?\s*after)/i;
const COVER_RE = /(?:封面|\bcover\b|\bopening\b)/i;
const TAG_RE = /(?:标签|主线卡|关键词|\btags?\b|\bchips?\b)/i;
const MEDIA_RE = /(?:照片|人物|海报|主视觉|插画|概念图|界面|截图|样机|hero|photo|portrait|poster|illustration|concept\s*art|interface|screenshot|mockup)/i;

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function outlineIntentRecord(slide) {
  return {
    title: text(slide && slide.title),
    message: text(slide && slide.message),
    layout: text(slide && slide.layout),
    visual: text(slide && slide.visual),
  };
}

function selectionText(slide) {
  const intent = outlineIntentRecord(slide);
  return [intent.title, intent.message, intent.layout, intent.visual]
    .filter(Boolean)
    .join("\n");
}

function visualSelectionText(slide) {
  const intent = outlineIntentRecord(slide);
  return [intent.layout, intent.visual].filter(Boolean).join("\n");
}

function semanticRule(kind, preferred, allowed, reason) {
  return {
    kind,
    preferred_layout_id: preferred,
    allowed_layout_ids: [...new Set(allowed)],
    reason,
  };
}

function outlineHasQuantitativeEvidence(slide, sourceMode = "") {
  const evidence = Array.isArray(slide && slide.evidence) ? slide.evidence : [];
  const userProvidedContent = sourceMode === "user_provided"
    ? [
      slide && slide.title,
      slide && slide.message,
      ...(Array.isArray(slide && slide.bullets) ? slide.bullets : []),
    ]
    : [];
  const content = [...evidence, ...userProvidedContent]
    .map(value => String(value || ""))
    .join(" ");
  return /\d|%|％|[$¥￥€£]|[一二三四五六七八九十百千万]+(?:次|年|届|名|个|项|座|枚|金牌|冠军)/.test(content);
}

function analyzeOutlineLayoutIntent(slide, sourceMode = "") {
  const all = selectionText(slide);
  const visual = visualSelectionText(slide);
  const layout = text(slide && slide.layout);

  if (QUADRANT_RE.test(visual)) {
    return semanticRule(
      "quadrant",
      "cards-grid-v1",
      ["cards-grid-v1"],
      "outline asks for quadrant cards, which require four parallel card regions"
    );
  }
  if (GANTT_RE.test(visual) || GANTT_RE.test(layout)) {
    return semanticRule(
      "gantt",
      "table-data-v1",
      ["table-data-v1"],
      "outline asks for an editable Gantt schedule with work packages across delivery phases"
    );
  }
  if (MATRIX_RE.test(visual)) {
    return semanticRule(
      "matrix",
      "table-data-v1",
      ["table-data-v1"],
      "outline asks for a matrix/table with explicit row and column relationships"
    );
  }
  if (BAR_CHART_RE.test(visual)) {
    return semanticRule(
      "bar-chart",
      "chart-bar-v1",
      ["chart-bar-v1", "chart-data-v1"],
      "outline asks for an editable bar or column chart"
    );
  }
  if (DATA_CHART_RE.test(visual)) {
    return semanticRule(
      "data-chart",
      "chart-data-v1",
      ["chart-data-v1"],
      "outline names a specific editable data-chart geometry"
    );
  }
  if (ARCHITECTURE_RE.test(visual)) {
    return semanticRule(
      "technical-architecture",
      "technical-diagram-v1",
      ["technical-diagram-v1"],
      "outline asks for a DiagramSpec technical architecture with editable nodes and edges"
    );
  }
  if (DATA_PIPELINE_RE.test(visual)) {
    return semanticRule(
      "data-pipeline",
      "technical-diagram-v1",
      ["technical-diagram-v1"],
      "outline asks for a DiagramSpec data pipeline with editable stages and flows"
    );
  }
  if (INTEGRATION_RE.test(visual)) {
    return semanticRule(
      "system-integration",
      "technical-diagram-v1",
      ["technical-diagram-v1"],
      "outline asks for a DiagramSpec system integration or data-flow map"
    );
  }
  if (DASHBOARD_RE.test(visual)) {
    const quantitative = outlineHasQuantitativeEvidence(slide, sourceMode);
    return quantitative
      ? semanticRule(
        "quantitative-dashboard",
        "kpi-grid-v1",
        ["kpi-grid-v1", "chart-data-v1", "chart-bar-v1"],
        "outline provides quantitative evidence for an editable KPI dashboard"
      )
      : semanticRule(
        "qualitative-dashboard",
        "dashboard-overview-v1",
        ["dashboard-overview-v1"],
        "outline asks for a dashboard concept without real values, so show editable metric domains without inventing numbers"
      );
  }
  if (KPI_RE.test(visual)) {
    return semanticRule(
      "kpi",
      "kpi-grid-v1",
      ["kpi-grid-v1", "chart-data-v1", "chart-bar-v1"],
      "outline asks for a KPI or metric board"
    );
  }
  if (COVER_RE.test(layout) && TAG_RE.test(visual) && !MEDIA_RE.test(visual)) {
    return semanticRule(
      "tagged-cover",
      "cover-editorial-v1",
      ["cover-editorial-v1"],
      "outline asks for a typography-led cover with tags rather than an image slot"
    );
  }
  if (COVER_RE.test(layout) && MEDIA_RE.test(visual)) {
    return semanticRule(
      "visual-cover",
      "cover-hero-v1",
      ["cover-hero-v1"],
      "outline explicitly asks for a cover image or hero visual"
    );
  }
  if (TIMELINE_RE.test(visual) || /(?:timeline|roadmap)/i.test(layout)) {
    return semanticRule(
      "timeline",
      "timeline-horizontal-v1",
      ["timeline-horizontal-v1"],
      "outline asks for ordered milestones on a time or roadmap axis"
    );
  }
  if (PROCESS_RE.test(visual)) {
    const prefersCards = /(?:cards?|卡片)/i.test(layout);
    return semanticRule(
      "staged-path",
      prefersCards ? "cards-grid-v1" : "timeline-horizontal-v1",
      ["cards-grid-v1", "timeline-horizontal-v1"],
      "outline asks for a staged path; numbered cards or a controlled timeline can express it"
    );
  }
  if (COMPARISON_RE.test(visual)) {
    return semanticRule(
      "comparison",
      "comparison-two-column-v1",
      ["comparison-two-column-v1", "table-data-v1"],
      "outline asks for an explicit side-by-side comparison"
    );
  }
  if (/^(?:timeline|roadmap|时间轴|路线图)$/i.test(layout)) {
    return semanticRule(
      "timeline",
      "timeline-horizontal-v1",
      ["timeline-horizontal-v1"],
      "outline layout explicitly requests a timeline"
    );
  }
  if (/^(?:matrix|table|矩阵|表格)$/i.test(layout)) {
    return semanticRule(
      "matrix",
      "table-data-v1",
      ["table-data-v1"],
      "outline layout explicitly requests a matrix/table"
    );
  }
  if (COVER_RE.test(layout) && MEDIA_RE.test(all)) {
    return semanticRule(
      "visual-cover",
      "cover-hero-v1",
      ["cover-hero-v1"],
      "outline explicitly asks for a visual-led cover"
    );
  }
  return null;
}

function expectedVisualItemCount(slide) {
  const visual = text(slide && slide.visual);
  if (!visual) return null;
  const match = visual.match(
    /(?:^|[^0-9一二三四五六七八九十])([0-9]{1,2}|[一二三四五六七八九十])\s*(?:条|个|项|类|段(?:式)?|象限|节点|阶段|主线|里程碑|卡片|标签)/u
  );
  if (!match) return null;
  const count = /^\d+$/.test(match[1]) ? Number(match[1]) : CHINESE_COUNTS[match[1]];
  return Number.isInteger(count) && count >= 2 && count <= 10 ? count : null;
}

function visualCollectionForSlide(slide) {
  if (!slide || !slide.props) return null;
  if (slide.layout_id === "cover-editorial-v1") {
    return { field: "tags", value: slide.props.tags };
  }
  if (slide.layout_id === "cards-grid-v1") {
    return { field: "items", value: slide.props.items };
  }
  if (slide.layout_id === "timeline-horizontal-v1") {
    return { field: "steps", value: slide.props.steps };
  }
  if (slide.layout_id === "table-data-v1") {
    return { field: "rows", value: slide.props.rows };
  }
  if (slide.layout_id === "closing-next-steps-v1") {
    return { field: "actions", value: slide.props.actions };
  }
  return null;
}

function validateOutlineVisualCardinality(slide, outlineSlide, basePath) {
  const expected = expectedVisualItemCount(outlineSlide);
  if (!expected) return [];
  const collection = visualCollectionForSlide(slide);
  if (!collection || !Array.isArray(collection.value)) return [];
  if (collection.value.length === expected) return [];
  return [
    `${basePath}.props.${collection.field}: outline visual explicitly requests ${expected} ` +
    `visual item(s), got ${collection.value.length}`,
  ];
}

module.exports = {
  analyzeOutlineLayoutIntent,
  expectedVisualItemCount,
  outlineHasQuantitativeEvidence,
  outlineIntentRecord,
  validateOutlineVisualCardinality,
};
