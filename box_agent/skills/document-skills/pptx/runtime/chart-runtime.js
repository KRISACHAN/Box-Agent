(function attachControlledDeckCharts(root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.__deckChartRuntime = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createControlledDeckCharts(root) {
  "use strict";

  const CHART_TYPES = new Set([
    "bar",
    "column",
    "line",
    "area",
    "pie",
    "donut",
    "radar",
  ]);
  const instances = new WeakMap();
  const mountedRoots = new Set();

  function numericValue(value) {
    const match = String(value == null ? "" : value)
      .replace(/,/g, "")
      .match(/-?\d+(?:\.\d+)?/);
    const parsed = match ? Number(match[0]) : 0;
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function normalizeSeries(series, categoryCount) {
    const rows = Array.isArray(series) ? series : [];
    return rows.slice(0, 4).map((item, index) => {
      const values = Array.isArray(item && item.values) ? item.values : [];
      return {
        name: String(item && item.name || `系列 ${index + 1}`).trim() || `系列 ${index + 1}`,
        values: Array.from({ length: categoryCount }, (_, valueIndex) =>
          numericValue(values[valueIndex])
        ),
      };
    });
  }

  function normalizeSpec(rawSpec) {
    const spec = rawSpec && typeof rawSpec === "object" ? rawSpec : {};
    if (Array.isArray(spec.data)) {
      const categories = spec.data.map(item => String(item && item.label || ""));
      return {
        version: 1,
        type: spec.orientation === "vertical" ? "column" : "bar",
        categories,
        series: [{
          name: String(spec.series || "数值"),
          values: spec.data.map(item => numericValue(item && item.value)),
        }],
        legend: "off",
        show_values: "on",
        animation: "on",
        value_suffix: "",
      };
    }

    const categories = (Array.isArray(spec.categories) ? spec.categories : [])
      .slice(0, 12)
      .map(value => String(value == null ? "" : value));
    const type = CHART_TYPES.has(spec.type) ? spec.type : "bar";
    const series = normalizeSeries(spec.series, categories.length);
    return {
      version: 1,
      type,
      categories,
      series: series.length ? series : [{ name: "数值", values: categories.map(() => 0) }],
      legend: ["auto", "on", "off"].includes(spec.legend) ? spec.legend : "auto",
      show_values: ["auto", "on", "off"].includes(spec.show_values)
        ? spec.show_values
        : "auto",
      animation: spec.animation === "off" ? "off" : "on",
      stacked: spec.stacked === "on" ? "on" : "off",
      value_suffix: String(spec.value_suffix || ""),
    };
  }

  function parseSpec(element) {
    const encoded = element && element.getAttribute("data-chart-spec");
    if (!encoded) return normalizeSpec({});
    try {
      return normalizeSpec(JSON.parse(encoded));
    } catch (error) {
      console.error("Invalid controlled chart spec", error);
      return normalizeSpec({});
    }
  }

  function normalizeHex(value, fallback) {
    const match = String(value || "").trim().match(/^#?([0-9a-f]{6})$/i);
    return match ? `#${match[1].toUpperCase()}` : fallback;
  }

  function mixHex(left, right, ratio) {
    const parse = value => normalizeHex(value, "#000000")
      .slice(1)
      .match(/.{2}/g)
      .map(part => parseInt(part, 16));
    const a = parse(left);
    const b = parse(right);
    const mixed = a.map((value, index) =>
      Math.round(value + (b[index] - value) * ratio)
        .toString(16)
        .padStart(2, "0")
    );
    return `#${mixed.join("")}`;
  }

  function themeTokens(element) {
    if (!root || !root.getComputedStyle) {
      return {
        primary: "#1E2BFA",
        text: "#111111",
        muted: "#6B6B6B",
        border: "#D1D2C8",
        background: "#FDFAE7",
        display: "Arial",
        body: "Arial",
      };
    }
    const style = root.getComputedStyle(element);
    const primary = normalizeHex(style.getPropertyValue("--deck-primary"), "#1E2BFA");
    const text = normalizeHex(style.getPropertyValue("--deck-text"), "#111111");
    const background = normalizeHex(style.getPropertyValue("--deck-bg"), "#FDFAE7");
    const chartColor = (index, fallback) => normalizeHex(
      style.getPropertyValue(`--deck-chart-${index}`),
      fallback
    );
    return {
      primary,
      text,
      background,
      muted: normalizeHex(style.getPropertyValue("--deck-muted"), "#6B6B6B"),
      border: normalizeHex(style.getPropertyValue("--deck-border"), "#D1D2C8"),
      display: style.getPropertyValue("--deck-display").trim() || "Arial",
      body: style.getPropertyValue("--deck-body").trim() || "Arial",
      palette: [
        chartColor(1, primary),
        chartColor(2, mixHex(primary, background, 0.36)),
        chartColor(3, text),
        chartColor(4, mixHex(primary, text, 0.46)),
      ],
    };
  }

  function valueLabel(spec) {
    if (spec.show_values === "on") return true;
    if (spec.show_values === "off") return false;
    return ["bar", "column", "pie", "donut"].includes(spec.type);
  }

  function legendVisible(spec) {
    if (spec.legend === "on") return true;
    if (spec.legend === "off") return false;
    return spec.series.length > 1;
  }

  function buildOption(rawSpec, tokens, options = {}) {
    const spec = normalizeSpec(rawSpec);
    const motionAllowed = options.motion !== false && spec.animation !== "off";
    const showValues = valueLabel(spec);
    const showLegend = legendVisible(spec);
    const suffix = spec.value_suffix;
    const axisLine = { lineStyle: { color: tokens.border, width: 1 } };
    const axisLabel = {
      color: tokens.muted,
      fontFamily: tokens.body,
      fontSize: 18,
      formatter: suffix ? `{value}${suffix}` : "{value}",
    };
    const categoryLabel = {
      color: tokens.text,
      fontFamily: tokens.body,
      fontSize: 18,
      overflow: "truncate",
      width: 230,
    };
    const base = {
      animation: motionAllowed,
      animationDuration: 860,
      animationDurationUpdate: 420,
      animationEasing: "cubicOut",
      animationDelay: index => Math.min(index * 55, 360),
      color: tokens.palette,
      backgroundColor: "transparent",
      textStyle: { fontFamily: tokens.body, color: tokens.text },
      aria: { enabled: true },
      tooltip: { show: options.interactive !== false, trigger: "axis" },
      legend: {
        show: showLegend,
        top: 0,
        right: 8,
        itemWidth: 18,
        itemHeight: 8,
        textStyle: { color: tokens.muted, fontFamily: tokens.body, fontSize: 16 },
      },
    };

    if (spec.type === "pie" || spec.type === "donut") {
      const series = spec.series[0] || { name: "数值", values: [] };
      return {
        ...base,
        tooltip: { show: options.interactive !== false, trigger: "item" },
        legend: {
          ...base.legend,
          show: spec.legend === "off" ? false : true,
          orient: "vertical",
          top: "middle",
          right: 18,
        },
        series: [{
          name: series.name,
          type: "pie",
          radius: spec.type === "donut" ? ["43%", "69%"] : [0, "70%"],
          center: [showLegend ? "42%" : "50%", "53%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: tokens.background, borderWidth: 3 },
          label: {
            show: showValues,
            color: tokens.text,
            fontFamily: tokens.body,
            fontSize: 17,
            formatter: suffix ? `{b}  {c}${suffix}` : "{b}  {c}",
          },
          emphasis: { scaleSize: 8 },
          data: spec.categories.map((name, index) => ({
            name,
            value: numericValue(series.values[index]),
          })),
        }],
      };
    }

    if (spec.type === "radar") {
      const maximum = spec.categories.map((_, categoryIndex) => {
        const max = Math.max(1, ...spec.series.map(series => numericValue(series.values[categoryIndex])));
        return Math.ceil(max * 1.16);
      });
      return {
        ...base,
        tooltip: { show: options.interactive !== false, trigger: "item" },
        radar: {
          center: ["50%", "54%"],
          radius: "70%",
          splitNumber: 4,
          axisName: { color: tokens.text, fontFamily: tokens.body, fontSize: 17 },
          axisLine: { lineStyle: { color: tokens.border } },
          splitLine: { lineStyle: { color: tokens.border } },
          splitArea: { areaStyle: { color: ["transparent", mixHex(tokens.primary, tokens.background, 0.93)] } },
          indicator: spec.categories.map((name, index) => ({ name, max: maximum[index] })),
        },
        series: [{
          type: "radar",
          data: spec.series.map(series => ({ name: series.name, value: series.values })),
          lineStyle: { width: 3 },
          areaStyle: { opacity: 0.1 },
          symbolSize: 8,
        }],
      };
    }

    const horizontal = spec.type === "bar";
    const categoryAxis = {
      type: "category",
      data: spec.categories,
      inverse: horizontal,
      axisLine,
      axisTick: { show: false },
      axisLabel: categoryLabel,
    };
    const valueAxis = {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel,
      splitLine: { lineStyle: { color: tokens.border, type: "dashed", opacity: 0.72 } },
    };
    const cartesianSeries = spec.series.map((series, seriesIndex) => {
      const isLine = spec.type === "line" || spec.type === "area";
      return {
        name: series.name,
        type: isLine ? "line" : "bar",
        data: series.values,
        stack: spec.stacked === "on" ? "total" : undefined,
        smooth: isLine,
        symbol: isLine ? "circle" : undefined,
        symbolSize: isLine ? 9 : undefined,
        showSymbol: isLine,
        lineStyle: isLine ? { width: 4 } : undefined,
        areaStyle: spec.type === "area" ? { opacity: 0.13 } : undefined,
        barMaxWidth: horizontal ? 34 : 58,
        itemStyle: isLine ? undefined : { borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
        label: {
          show: showValues,
          position: horizontal ? "right" : "top",
          color: seriesIndex === 0 ? tokens.primary : tokens.text,
          fontFamily: tokens.display,
          fontSize: 17,
          fontWeight: 600,
          formatter: suffix ? `{c}${suffix}` : "{c}",
        },
        emphasis: { focus: "series" },
      };
    });
    return {
      ...base,
      grid: {
        left: horizontal ? 250 : 54,
        right: showValues ? 78 : 34,
        top: showLegend ? 62 : 28,
        bottom: horizontal ? 32 : 84,
        containLabel: false,
      },
      xAxis: horizontal ? valueAxis : categoryAxis,
      yAxis: horizontal ? categoryAxis : valueAxis,
      series: cartesianSeries,
    };
  }

  function exportMode() {
    if (!root || !root.location) return false;
    return Boolean(root.navigator && root.navigator.webdriver) ||
      new URLSearchParams(root.location.search).get("mode") === "export";
  }

  function renderElement(element, options = {}) {
    if (!element || !element.isConnected) return null;
    const container = element.querySelector("[data-chart-canvas]");
    if (!container || !root || !root.echarts) {
      element.classList.add("chart-runtime-missing");
      return null;
    }
    let chart = instances.get(container);
    if (!chart || chart.isDisposed && chart.isDisposed()) {
      chart = root.echarts.init(container, null, { renderer: "svg" });
      instances.set(container, chart);
    }
    const spec = parseSpec(element);
    const reduceMotion = root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const motion = !exportMode() && !reduceMotion && options.motion !== false;
    if (options.replay) chart.clear();
    chart.setOption(buildOption(spec, themeTokens(element), {
      motion,
      interactive: !exportMode(),
    }), true);
    chart.resize();
    mountedRoots.add(element);
    element.classList.remove("chart-runtime-missing");
    element.classList.add("chart-runtime-ready");
    element.setAttribute("data-chart-renderer", "echarts-svg");
    return chart;
  }

  function cleanup() {
    mountedRoots.forEach(element => {
      if (element.isConnected) return;
      const container = element.querySelector("[data-chart-canvas]");
      const chart = container ? instances.get(container) : null;
      if (chart && !(chart.isDisposed && chart.isDisposed())) chart.dispose();
      mountedRoots.delete(element);
    });
  }

  function renderAll(context, options = {}) {
    cleanup();
    const scope = context && context.querySelectorAll ? context : root.document;
    if (!scope) return [];
    return Array.from(scope.querySelectorAll("[data-pptx-chart]"))
      .map(element => renderElement(element, options))
      .filter(Boolean);
  }

  function replaySlide(index) {
    if (!root || !root.document) return;
    const slide = root.document.querySelectorAll(".slide")[Number(index) || 0];
    if (!slide) return;
    renderAll(slide, { replay: true });
  }

  function mount() {
    if (!root || !root.document) return;
    renderAll(root.document, { motion: !exportMode() });
    let resizeTimer = null;
    root.addEventListener("resize", () => {
      if (resizeTimer) root.clearTimeout(resizeTimer);
      resizeTimer = root.setTimeout(() => {
        cleanup();
        mountedRoots.forEach(element => {
          const container = element.querySelector("[data-chart-canvas]");
          const chart = container ? instances.get(container) : null;
          if (chart) chart.resize();
        });
      }, 80);
    });
    root.addEventListener("box-agent:deck-change", () => {
      root.requestAnimationFrame(() => renderAll(root.document, { motion: false }));
    });
    root.addEventListener("box-agent:deck-present", event => {
      if (event.detail && event.detail.presenting) replaySlide(event.detail.index);
    });
    root.addEventListener("box-agent:deck-present-slide", event => {
      replaySlide(event.detail && event.detail.index);
    });
  }

  if (root && root.document) {
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", mount, { once: true });
    } else {
      mount();
    }
  }

  return {
    buildOption,
    normalizeSpec,
    parseSpec,
    renderAll,
    renderElement,
    replaySlide,
  };
});
