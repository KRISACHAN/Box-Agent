"use strict";

const { familyForTheme } = require("./composition_core.js");

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function selectionText(value) {
  const parts = [];
  const visit = item => {
    if (typeof item === "string") {
      const text = item.trim();
      if (text) parts.push(text);
      return;
    }
    if (Array.isArray(item)) {
      item.forEach(visit);
      return;
    }
    if (isPlainObject(item)) Object.values(item).forEach(visit);
  };
  visit(value);
  return parts.join("\n").normalize("NFKC").toLowerCase();
}

function selectionIntentText(value) {
  if (!isPlainObject(value)) return selectionText(value);
  const parts = [];
  const add = item => {
    const text = selectionText(item);
    if (text) parts.push(text);
  };
  ["title", "deck_title", "prompt", "brief", "request"].forEach(key => add(value[key]));
  const outline = isPlainObject(value.outline) ? value.outline : null;
  if (outline) {
    ["deck_goal", "audience", "storyline", "tone", "title"].forEach(key => add(outline[key]));
    (Array.isArray(outline.slides) ? outline.slides : []).forEach(slide => {
      if (!isPlainObject(slide)) return;
      ["title", "message", "visual", "layout_id"].forEach(key => add(slide[key]));
    });
  } else {
    add(value.source_text);
    add(value.source_facts);
  }
  return parts.length ? parts.join("\n") : selectionText(value);
}

function themeProfile(theme) {
  const selection = isPlainObject(theme && theme.selection) ? theme.selection : {};
  const mood = Array.isArray(selection.mood_keywords) ? selection.mood_keywords : [];
  const industry = Array.isArray(selection.industry_fit) ? selection.industry_fit : [];
  return {
    mood: selectionText(mood),
    mood_terms: mood.map(value => selectionText(value)).filter(Boolean),
    industry: selectionText(industry),
    industry_terms: industry.map(value => selectionText(value)).filter(Boolean),
    description: selectionText(theme && theme.description),
    scheme: String(selection.scheme || "").trim().toLowerCase(),
    formality: String(selection.formality || "").trim().toLowerCase(),
    fallback: selection.fallback === true,
    family: familyForTheme(theme),
  };
}

const NEGATED_PREFERENCE_CLAUSE_SOURCE =
  "(?:不要|避免|拒绝|不用|不使用|禁用|\\b(?:do\\s+not|don't|avoid|without|never|no)\\b)[^。；;\\n]{0,96}";

function inferPreferences(content) {
  const text = selectionText(content);
  const negatedClauses = text.match(
    new RegExp(NEGATED_PREFERENCE_CLAUSE_SOURCE, "gi")
  ) || [];
  const negatedText = negatedClauses.join("\n");
  const positiveText = text.replace(
    new RegExp(NEGATED_PREFERENCE_CLAUSE_SOURCE, "gi"),
    " "
  );
  const avoids = subject => new RegExp(`(?:${subject})`, "i").test(negatedText);
  return {
    text,
    positive_text: positiveText,
    wants_light: /(?:浅色|浅底|白底|明亮|亮色|light[- ]?(?:background|canvas|theme)|bright|airy)/i.test(positiveText),
    rejects_dark: avoids("深色|暗色|黑底|高冷|dark|black background"),
    wants_friendly: /(?:亲和|友好|亲切|欢迎|不端着|有温度|friendly|welcoming|approachable)/i.test(positiveText),
    rejects_friendly: avoids("亲和|友好|亲切|欢迎|friendly|welcoming|approachable"),
    wants_soft: /(?:柔和|粉彩|低饱和|温柔|\bsoft\b|pastel|gentle)/i.test(positiveText),
    wants_clean: /(?:清爽|干净|简洁|留白|不拥挤|clean|airy|uncluttered|minimal)/i.test(positiveText),
    wants_lively: /(?:活力|活泼|轻松|有趣|lively|playful|cheerful|energetic)/i.test(positiveText),
    rejects_lively: avoids("活力|活泼|轻松|有趣|lively|playful|cheerful|energetic"),
    wants_comic: /(?:漫画|分镜|对话气泡|对白气泡|拟声词|网点纸|波普漫画|漫画书|连环画|comic(?:[- ]?book)?|comic\s+panel|graphic\s+novel|storyboard|speech\s+bubble|halftone|manga|pop[- ]?art)/i.test(positiveText),
    rejects_comic: avoids("漫画|分镜|对话气泡|对白气泡|拟声词|网点纸|波普漫画|comic(?:[- ]?book)?|comic\\s+panel|graphic\\s+novel|storyboard|speech\\s+bubble|halftone|manga|pop[- ]?art"),
    wants_pixel: /(?:像素风|像素艺术|像素街机|复古游戏|电玩|街机|点阵|8[- ]?bit|16[- ]?bit|pixel(?:[- ]?art|[- ]?style)?|retro[- ]?(?:game|gaming)|arcade|game\s+ui|crt|neon\s+arcade)/i.test(positiveText),
    rejects_pixel: avoids("像素风|像素艺术|像素街机|复古游戏|电玩|街机|点阵|8[- ]?bit|16[- ]?bit|pixel(?:[- ]?art|[- ]?style)?|retro[- ]?(?:game|gaming)|arcade|game\\s+ui|crt|neon\\s+arcade"),
    wants_restrained_palette: /(?:一(?:到|至)?两(?:个|种)?.{0,8}(?:色|颜色)|一两个.{0,8}(?:色|颜色)|少量.{0,8}点缀|颜色干净|克制配色|limited palette|one or two accent)/i.test(positiveText),
    wants_cool_palette: /(?:冷色|深蓝|海军蓝|钢灰|蓝灰|浅灰|cool(?:[- ]tone|[- ]palette)?|deep navy|navy blue|steel gr[ae]y|blue gr[ae]y)/i.test(positiveText),
    formal_solution_review: /(?:评标|投标|招标|采购负责人|客户交付|解决方案|采购评审|技术评审|bid evaluation|tender|procurement|solution proposal|client deliverable)/i.test(positiveText),
    internal_training: /(?:新员工|员工入职|入职培训|内部培训|员工培训|迎新|onboarding|employee orientation|internal training|training deck)/i.test(positiveText),
    enterprise_context: /(?:企业|集团|公司|会议室|职场|组织|b2b|enterprise|corporate|business|workplace)/i.test(positiveText),
    rejects_collage: avoids("拼贴|collage"),
    rejects_retro: avoids("复古|怀旧|像素|retro|vintage|nostalgia|pixel"),
    rejects_handwritten: avoids("手绘|手写|便签|hand[- ]?drawn|handwritten|sticky notes"),
    rejects_stiff: /(?:不端着|不要高冷|不高冷|不严肃|not stiff|not cold|approachable)/i.test(text),
  };
}

function profileHas(profile, pattern) {
  return pattern.test(`${profile.mood}\n${profile.industry}\n${profile.description}`);
}

const THEME_KEYWORD_RULES = Object.freeze([
  Object.freeze({
    theme_id: "technical-blueprint",
    signal: "keyword rule: architecture and infrastructure",
    pattern: /(?:系统架构|技术架构|架构图|系统集成|系统对接|系统连接|云基础设施|平台工程|运行时架构|接口架构|事件总线|消息队列|数据管道|数据流|CDC|system\s+architecture|technical\s+architecture|architecture\s+diagram|system\s+integration|system\s+connection|cloud\s+infrastructure|platform\s+engineering|runtime\s+architecture|event\s+bus|message\s+queue|data\s+pipeline|data\s+flow)/i,
    weight: 18,
  }),
  Object.freeze({
    theme_id: "product-console",
    signal: "keyword rule: SaaS and product interface",
    pattern: /(?:SaaS|软件产品|AI\s*产品|产品介绍|产品发布|产品演示|核心功能|功能演示|使用流程|产品价值|产品界面|控制台|工作台|客户端界面|开发者平台|product\s+introduction|product\s+launch|product\s+demo|core\s+features?|feature\s+demo|usage\s+flow|product\s+value|product\s+interface|software\s+product|AI\s+product|developer\s+platform|app\s+console)/i,
    weight: 18,
  }),
  Object.freeze({
    theme_id: "data-intelligence",
    signal: "keyword rule: KPI and business intelligence",
    pattern: /(?:商业智能|经营分析|数据分析|指标复盘|财务分析|经营看板|数据看板|核心指标|KPI|同比|环比|business\s+intelligence|data\s+analytics|KPI\s+review|operating\s+review|performance\s+dashboard|metrics?\s+review|growth\s+analytics)/i,
    weight: 18,
  }),
  Object.freeze({
    theme_id: "signal",
    signal: "keyword rule: board risk and advisory",
    pattern: /(?:董事会|风险委员会|年度风险|风险分析|风险治理|战略建议|预警信号|board\s+(?:risk|review|presentation)|risk\s+(?:analysis|governance|committee)|strategic\s+recommendations?|early\s+warning\s+signals?)/i,
    weight: 17,
  }),
  Object.freeze({
    theme_id: "soft-editorial",
    signal: "keyword rule: qualitative user research",
    pattern: /(?:用户访谈|用户研究|定性研究|访谈洞察|研究发现|研究方法|user\s+interviews?|user\s+research|qualitative\s+research|interview\s+insights?|research\s+findings?)/i,
    weight: 16,
  }),
  Object.freeze({
    theme_id: "pink-script",
    signal: "keyword rule: premium beauty launch",
    pattern: /(?:(?:高端|奢华|高级感|精品|premium|luxury|luxe)[^。；;\n]{0,28}(?:美妆|护肤|时尚|珠宝|香水|beauty|skincare|fashion|jewelry|fragrance)|(?:美妆|护肤|时尚|珠宝|香水|beauty|skincare|fashion|jewelry|fragrance)[^。；;\n]{0,28}(?:高端|奢华|高级感|精品|premium|luxury|luxe))/i,
    weight: 7,
  }),
]);

const INDUSTRY_MATCH_RULES = Object.freeze([
  Object.freeze({
    signal: "industry match: technical systems",
    content: /(?:系统架构|技术架构|系统集成|云平台|云基础设施|平台工程|运行时|接口|数据管道|架构图|system\s+architecture|technical\s+architecture|system\s+integration|cloud\s+(?:platform|infrastructure)|platform\s+engineering|runtime|API\s+platform|data\s+pipeline)/i,
    profile: /(?:system architecture|cloud infrastructure|platform engineering|system integration|enterprise technology|developer tools|系统架构|云基础设施|平台工程|系统集成)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "industry match: software product",
    content: /(?:SaaS|软件产品|AI\s*产品|产品发布|产品演示|功能演示|产品界面|开发者平台|product\s+(?:launch|demo|interface|management)|software\s+product|AI\s+product|developer\s+platform|B2B\s+software)/i,
    profile: /(?:SaaS|software product|AI product|product management|developer platform|B2B software|软件产品|AI 产品|产品发布|开发者平台)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "industry match: analytics and operations",
    content: /(?:商业智能|数据分析|经营分析|财务分析|指标复盘|经营看板|数据看板|KPI|同比|环比|收入|成本|business\s+intelligence|data\s+analytics|operating\s+(?:analysis|review)|finance\s+analysis|KPI\s+review|dashboard|metrics?|revenue|growth\s+analytics)/i,
    profile: /(?:business intelligence|data analytics|KPI review|finance|operations|growth analytics|商业智能|数据分析|经营分析|财务分析|指标复盘)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "industry match: sustainability",
    content: /(?:可持续|ESG|气候|环保|新能源|绿色发展|sustainability|climate|environment|renewable|green\s+transition)/i,
    profile: /(?:sustainability|organic|森林绿|有机|可持续|环境|能源)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "industry match: luxury and beauty",
    content: /(?:奢侈|高端|美妆|护肤|时尚|珠宝|香水|luxury|premium|beauty|skincare|fashion|jewelry|fragrance)/i,
    profile: /(?:luxury|beauty|fashion|consumer product|creative brand|portfolio)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "industry match: education and training",
    content: /(?:教育|培训|课堂|课程|学校|校园|新员工|入职|工作坊|education|training|classroom|course|school|campus|onboarding|workshop)/i,
    profile: /(?:education|training|classroom|course|school|campus|workshop|children|research notes)/i,
    weight: 5,
  }),
  Object.freeze({
    signal: "industry match: board and advisory",
    content: /(?:董事会|投资人|投标|评标|咨询方案|政策|法务|board|investor|procurement|tender|consulting|policy|legal|advisory)/i,
    profile: /(?:board presentation|investor deck|procurement|bid evaluation|consulting|policy|legal|advisory)/i,
    weight: 5,
  }),
]);

const MOOD_MATCH_RULES = Object.freeze([
  Object.freeze({
    signal: "mood match: technical precision",
    content: /(?:技术感|精密|严谨|系统化|工程感|蓝图|technical|precise|systematic|engineering|blueprint)/i,
    profile: /(?:technical|precise|systematic|structured|engineering|blueprint|技术|精密|系统化|严谨|蓝图)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "mood match: clean modern product",
    content: /(?:现代|清爽|产品化|模块化|精致|简洁|modern|clean|product-led|polished|modular|minimal)/i,
    profile: /(?:modern|clean|product-led|polished|modular|现代|清爽|产品化|模块化)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "mood match: analytical evidence",
    content: /(?:分析感|数据驱动|证据驱动|理性|高密度|analytical|data-driven|evidence-led|intelligent|high density)/i,
    profile: /(?:analytical|intelligent|evidence-led|precise|authoritative|high density|分析|智能|证据驱动|高密度)/i,
    weight: 7,
  }),
  Object.freeze({
    signal: "mood match: institutional authority",
    content: /(?:权威|可信|稳重|正式|机构感|专业|authoritative|trustworthy|credible|weighty|formal|professional)/i,
    profile: /(?:institutional|trustworthy|authoritative|credible|weighty|professional|机构|可信|稳重|专业)/i,
    weight: 4,
  }),
  Object.freeze({
    signal: "mood match: soft warmth",
    content: /(?:柔和|温暖|亲和|安静|留白|粉彩|\bsoft\b|warm|friendly|quiet|airy|pastel|gentle)/i,
    profile: /(?:\bsoft\b|warm|friendly|quiet|pastel|literary|considered|柔和|亲和|留白|沉静)/i,
    weight: 5,
  }),
  Object.freeze({
    signal: "mood match: premium atmosphere",
    content: /(?:高级感|奢华|精品|夜色|情绪化|premium|luxury|luxe|nocturnal|moody|cinematic)/i,
    profile: /(?:premium|luxury|luxe|nocturnal|moody|atmospheric|奢华|夜色)/i,
    weight: 5,
  }),
  Object.freeze({
    signal: "mood match: bold energy",
    content: /(?:大胆|醒目|强视觉|活力|有趣|bold|graphic|energetic|playful|punchy|high contrast)/i,
    profile: /(?:bold|graphic|energetic|playful|punchy|high contrast|大胆|醒目|活泼)/i,
    weight: 4,
  }),
  Object.freeze({
    signal: "mood match: literary editorial",
    content: /(?:文学|编辑感|杂志感|人文|克制|沉静|literary|editorial|magazine|scholarly|patient|quiet)/i,
    profile: /(?:literary|editorial|magazine|scholarly|patient|quiet|文学|编辑|杂志|沉静)/i,
    weight: 4,
  }),
]);

function metadataTermMatches(text, term) {
  const normalized = selectionText(term);
  if (!normalized || normalized.length < 2) return false;
  if (/^[a-z0-9][a-z0-9+.#\s-]*$/i.test(normalized)) {
    const escaped = normalized
      .replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
      .replace(/\s+/g, "\\s+");
    return new RegExp(`(?:^|[^a-z0-9])${escaped}(?:$|[^a-z0-9])`, "i").test(text);
  }
  return text.includes(normalized);
}

function directMetadataHits(text, terms) {
  return [...new Set((terms || []).filter(term => metadataTermMatches(text, term)))];
}

function applyTaxonomyMatches(rules, dimension, text, profile, add) {
  rules.forEach(rule => {
    if (!rule.content.test(text)) return;
    const profileText = dimension === "industry" ? profile.industry : profile.mood;
    if (rule.profile.test(profileText)) add(rule.signal, rule.weight);
  });
}

function inferTheme(themes, content, defaultThemeId = "blue-professional") {
  const candidates = Array.isArray(themes) ? themes.filter(theme => theme && theme.id) : [];
  const preferences = inferPreferences(content);
  const intentText = selectionIntentText(content);
  const intentPreferences = inferPreferences(intentText);
  const intentPositiveText = intentPreferences.positive_text;
  const scoreByTheme = new Map();
  const matchesByTheme = new Map();

  candidates.forEach(theme => {
    const profile = themeProfile(theme);
    let score = theme.id === defaultThemeId ? 0.25 : 0;
    const matches = [];
    const add = (signal, weight) => {
      score += weight;
      matches.push({ signal, weight });
    };

    if (profile.fallback) add("fallback theme", -1);

    THEME_KEYWORD_RULES.forEach(rule => {
      if (theme.id === rule.theme_id && rule.pattern.test(intentPositiveText)) {
        add(rule.signal, rule.weight);
      }
    });

    const industryHits = directMetadataHits(intentPositiveText, profile.industry_terms);
    if (industryHits.length) {
      add(`industry metadata: ${industryHits.slice(0, 2).join(", ")}`, Math.min(6, industryHits.length * 3));
    }
    applyTaxonomyMatches(
      INDUSTRY_MATCH_RULES,
      "industry",
      intentPositiveText,
      profile,
      add
    );

    const moodHits = directMetadataHits(intentPositiveText, profile.mood_terms);
    if (moodHits.length) {
      add(`mood metadata: ${moodHits.slice(0, 2).join(", ")}`, Math.min(4, moodHits.length * 2));
    }
    applyTaxonomyMatches(
      MOOD_MATCH_RULES,
      "mood",
      intentPositiveText,
      profile,
      add
    );

    if (preferences.wants_light) {
      if (profile.scheme.includes("light")) add("light canvas", 6);
      else if (profile.scheme === "mixed") add("mixed canvas conflicts with light-first brief", -3);
      else if (profile.scheme === "dark") add("dark canvas conflicts with light-first brief", -8);
    }
    if (preferences.rejects_dark) {
      if (profile.scheme.includes("light")) add("explicit dark-theme opt-out", 4);
      else if (profile.scheme === "mixed") add("explicit dark-theme opt-out", -4);
      else if (profile.scheme === "dark") add("explicit dark-theme opt-out", -12);
    }

    if (preferences.wants_friendly) {
      if (profileHas(profile, /(?:friendly|亲和|cheerful|social)/i)) add("friendly mood", 7);
      if (profileHas(profile, /(?:warm|\bsoft\b|pastel|considered|温暖|柔和)/i)) {
        add("warm or soft supporting mood", 2);
      }
      if (profileHas(profile, /(?:raw|brutalist|authoritative|technical|neon|硬朗|高冷)/i)) {
        add("hard or cold mood conflicts with friendly brief", -3);
      }
    }

    if (preferences.wants_soft) {
      if (profileHas(profile, /(?:\bsoft\b|pastel|quiet|sage|blush|peach|柔和|粉彩|鼠尾草|桃色)/i)) {
        add("soft palette mood", 7);
      }
      if (profileHas(profile, /(?:warm|friendly|亲和)/i)) add("warm supporting palette", 2);
      if (profileHas(profile, /(?:bold|raw|neon|high contrast|硬朗|高饱和)/i)) {
        add("hard palette conflicts with soft brief", -4);
      }
    }

    if (preferences.wants_clean) {
      if (profileHas(profile, /(?:quiet|minimal|considered|modern|precise|restrained|editorial|bichromatic|克制|现代|严谨|留白)/i)) {
        add("clean and ordered mood", 3);
      }
      if (profileHas(profile, /(?:collage|sticky notes|handmade|pixel|neon|zine|raw|拼贴|便利贴|手作|像素)/i)) {
        add("busy visual language conflicts with clean brief", -4);
      }
    }

    if (preferences.wants_lively) {
      if (profileHas(profile, /(?:playful|cheerful|friendly|energetic|活泼|亲和)/i)) {
        add("lively supporting mood", 3);
      } else if (profileHas(profile, /(?:quiet|literary|沉静)/i)) {
        add("quiet mood underplays requested energy", -1);
      }
    }

    if (preferences.wants_comic) {
      if (profileHas(profile, /(?:comic|graphic novel|storyboard|speech bubble|halftone|manga|pop art|漫画|分镜|对话气泡|拟声词|网点纸|波普漫画)/i)) {
        add("comic-panel visual language", 18);
      } else if (profileHas(profile, /(?:playful|graphic|bold|pop|活泼|图形)/i)) {
        add("graphic supporting mood for comic brief", 2);
      }
    }
    if (
      preferences.rejects_comic
      && profileHas(profile, /(?:comic|graphic novel|storyboard|speech bubble|halftone|manga|pop art|漫画|分镜|对话气泡|拟声词|网点纸|波普漫画)/i)
    ) {
      add("explicit comic-style opt-out", -20);
    }

    if (preferences.wants_pixel) {
      if (profileHas(profile, /(?:pixel[- ]art|8[- ]?bit|16[- ]?bit|arcade|retro-tech|cyberpunk|像素街机|像素艺术|霓虹街机)/i)) {
        add("pixel-arcade visual language", 18);
      } else if (profileHas(profile, /(?:pixel|retro|nostalgia|gaming|像素|复古|怀旧)/i)) {
        add("retro supporting mood for pixel brief", 2);
      }
    }
    if (
      preferences.rejects_pixel
      && profileHas(profile, /(?:pixel|8[- ]?bit|16[- ]?bit|arcade|retro-tech|cyberpunk|像素|街机|电玩)/i)
    ) {
      add("explicit pixel-style opt-out", -20);
    }

    if (
      preferences.rejects_friendly
      && profileHas(profile, /(?:friendly|approachable|welcoming|cheerful|亲和|友好|欢迎)/i)
    ) {
      add("explicit friendly-style opt-out", -14);
    }
    if (
      preferences.rejects_lively
      && profileHas(profile, /(?:playful|cheerful|energetic|upbeat|fun|活泼|活力)/i)
    ) {
      add("explicit lively-style opt-out", -14);
    }

    if (preferences.internal_training) {
      if (/training/i.test(profile.industry)) add("training industry fit", 8);
      else if (/education/i.test(profile.industry)) add("education industry fit", 6);
      else if (/workshop/i.test(profile.industry)) add("workshop industry fit", 4);
      else if (/community/i.test(profile.industry)) add("community industry fit", 3);
      else if (/startup/i.test(profile.industry)) add("startup industry fit", 2);
    }

    if (preferences.enterprise_context) {
      if (/(?:enterprise|business|technology|consulting|b2b)/i.test(profile.industry)) {
        add("enterprise industry fit", 4);
      } else if (/startup/i.test(profile.industry)) {
        add("startup industry fit", 2);
      }
      if (/^medium(?:-low|-high)?$/.test(profile.formality)) add("workplace formality fit", 2);
      else if (profile.formality === "low") add("too informal for workplace training", -3);
    }

    if (preferences.rejects_stiff && profile.formality === "high") {
      add("high formality conflicts with approachable brief", -2);
    }

    if (preferences.wants_restrained_palette) {
      if (profileHas(profile, /(?:bichromatic|monochrome|restrained|quiet|\bsoft\b|pastel|克制|柔和)/i)) {
        add("restrained accent palette", 4);
      }
      if (profileHas(profile, /(?:multicolor|rainbow|chromatic|neon|多彩|高饱和)/i)) {
        add("multicolor palette conflicts with limited accents", -5);
      }
    }

    if (preferences.wants_cool_palette) {
      if (profile.scheme.includes("cool")) add("cool light palette", 8);
      if (profileHas(profile, /(?:cool|navy|steel gr[ae]y|blue gr[ae]y|冷色|深蓝|钢灰|蓝灰)/i)) {
        add("navy and steel palette", 5);
      }
      if (profile.scheme.includes("warm") || profileHas(profile, /(?:warm paper|warm parchment|暖色|暖黄)/i)) {
        add("warm palette conflicts with cool brief", -8);
      }
    }

    if (preferences.formal_solution_review) {
      if (/(?:procurement|bid evaluation|consulting|enterprise|b2b|technology|advisory)/i.test(profile.industry)) {
        add("formal solution-review industry fit", 6);
      }
      if (profile.formality === "high") add("high-formality review fit", 4);
      else if (profile.formality === "low") add("too informal for formal review", -6);
    }

    if (preferences.rejects_collage) {
      if (profile.family === "playful-collage") add("explicit collage opt-out", -14);
      if (profileHas(profile, /(?:collage|sticky notes|handmade|拼贴|便利贴|手作)/i)) {
        add("explicit collage opt-out", -10);
      }
    }
    if (preferences.rejects_retro) {
      if (profile.family === "retro-interface") add("explicit retro opt-out", -14);
      if (profileHas(profile, /(?:retro|vintage|nostalgia|pixel|zine|riso|复古|怀旧|像素)/i)) {
        add("explicit retro opt-out", -12);
      }
    }
    if (
      preferences.rejects_handwritten
      && profileHas(profile, /(?:handwritten|handmade|hand[- ]?drawn|sticky notes|annotation|手写|手作|便签)/i)
    ) {
      add("explicit handwritten opt-out", -14);
    }

    if (
      theme.id === "soft-editorial"
      && preferences.wants_light
      && preferences.wants_soft
      && preferences.wants_clean
      && preferences.wants_restrained_palette
    ) {
      add("soft clean light signature", 8);
    }
    if (
      theme.id === "consulting-navy"
      && preferences.wants_light
      && preferences.wants_cool_palette
      && preferences.formal_solution_review
    ) {
      add("cool consulting review signature", 8);
    }
    if (
      theme.id === "playful"
      && preferences.wants_friendly
      && preferences.wants_lively
      && !preferences.rejects_friendly
      && !preferences.rejects_lively
      && !preferences.rejects_collage
    ) {
      add("friendly lively signature", 6);
    }
    if (
      theme.id === "pin-and-paper"
      && preferences.internal_training
      && !preferences.rejects_handwritten
    ) {
      add("training workshop signature", 4);
    }
    if (theme.id === "comic-panel" && preferences.wants_comic && !preferences.rejects_comic) {
      add("comic-panel signature", 10);
    }
    if (theme.id === "8-bit-orbit" && preferences.wants_pixel && !preferences.rejects_pixel) {
      add("8-bit-orbit signature", 10);
    }
    if (
      theme.id === defaultThemeId
      && preferences.enterprise_context
      && !preferences.wants_friendly
      && !preferences.wants_soft
    ) {
      add("neutral enterprise fallback", 3);
    }

    scoreByTheme.set(theme.id, score);
    matchesByTheme.set(theme.id, matches);
  });

  const ranked = candidates
    .map((theme, index) => ({ theme_id: theme.id, score: scoreByTheme.get(theme.id) || 0, index }))
    .sort((left, right) => right.score - left.score || left.index - right.index);
  const top = ranked[0] || { theme_id: defaultThemeId, score: 0, index: 0 };
  const runnerUp = ranked[1] || { score: 0 };
  const margin = top.score - runnerUp.score;
  const confidence = top.score >= 18 && margin >= 2
    ? "high"
    : top.score >= 10 && margin >= 1
      ? "medium"
      : "low";
  const themeId = confidence === "low" ? defaultThemeId : top.theme_id;
  return {
    theme_id: themeId,
    source: confidence === "low" ? "fallback_default" : "content_inference",
    confidence,
    score: scoreByTheme.get(themeId) || 0,
    margin,
    matched_signals: matchesByTheme.get(themeId) || [],
    ranking: ranked.slice(0, 5).map(({ theme_id, score }) => ({ theme_id, score })),
  };
}

module.exports = {
  inferPreferences,
  inferTheme,
  selectionIntentText,
  selectionText,
};
