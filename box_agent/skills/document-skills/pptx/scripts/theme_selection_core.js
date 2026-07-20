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

function themeProfile(theme) {
  const selection = isPlainObject(theme && theme.selection) ? theme.selection : {};
  const mood = Array.isArray(selection.mood_keywords) ? selection.mood_keywords : [];
  const industry = Array.isArray(selection.industry_fit) ? selection.industry_fit : [];
  return {
    mood: selectionText(mood),
    industry: selectionText(industry),
    description: selectionText(theme && theme.description),
    scheme: String(selection.scheme || "").trim().toLowerCase(),
    formality: String(selection.formality || "").trim().toLowerCase(),
    fallback: selection.fallback === true,
    family: familyForTheme(theme),
  };
}

function inferPreferences(content) {
  const text = selectionText(content);
  const avoids = subject => new RegExp(
    `(?:不要|避免|拒绝|不用|不使用|禁用|no|avoid)[^。；;\\n]{0,20}(?:${subject})`,
    "i"
  ).test(text);
  return {
    text,
    wants_light: /(?:浅色|浅底|白底|明亮|亮色|light[- ]?(?:background|canvas|theme)|bright|airy)/i.test(text),
    rejects_dark: avoids("深色|暗色|黑底|高冷|dark|black background"),
    wants_friendly: /(?:亲和|友好|亲切|欢迎|不端着|有温度|friendly|welcoming|approachable)/i.test(text),
    wants_soft: /(?:柔和|粉彩|低饱和|温柔|soft|pastel|gentle)/i.test(text),
    wants_clean: /(?:清爽|干净|简洁|留白|不拥挤|clean|airy|uncluttered|minimal)/i.test(text),
    wants_lively: /(?:活力|活泼|轻松|有趣|lively|playful|cheerful|energetic)/i.test(text),
    wants_restrained_palette: /(?:一(?:到|至)?两(?:个|种)?.{0,8}(?:色|颜色)|一两个.{0,8}(?:色|颜色)|少量.{0,8}点缀|颜色干净|克制配色|limited palette|one or two accent)/i.test(text),
    internal_training: /(?:新员工|员工入职|入职培训|内部培训|员工培训|迎新|onboarding|employee orientation|internal training|training deck)/i.test(text),
    enterprise_context: /(?:企业|公司|会议室|职场|组织|b2b|enterprise|corporate|business|workplace)/i.test(text),
    rejects_collage: avoids("拼贴|collage"),
    rejects_retro: avoids("复古|怀旧|像素|retro|vintage|nostalgia|pixel"),
    rejects_handwritten: avoids("手绘|手写|便签|hand[- ]?drawn|handwritten|sticky notes"),
    rejects_stiff: /(?:不端着|不要高冷|不高冷|不严肃|not stiff|not cold|approachable)/i.test(text),
  };
}

function profileHas(profile, pattern) {
  return pattern.test(`${profile.mood}\n${profile.industry}\n${profile.description}`);
}

function inferTheme(themes, content, defaultThemeId = "blue-professional") {
  const candidates = Array.isArray(themes) ? themes.filter(theme => theme && theme.id) : [];
  const preferences = inferPreferences(content);
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
      if (profileHas(profile, /(?:warm|soft|pastel|considered|温暖|柔和)/i)) {
        add("warm or soft supporting mood", 2);
      }
      if (profileHas(profile, /(?:raw|brutalist|authoritative|technical|neon|硬朗|高冷)/i)) {
        add("hard or cold mood conflicts with friendly brief", -3);
      }
    }

    if (preferences.wants_soft) {
      if (profileHas(profile, /(?:soft|pastel|quiet|sage|blush|peach|柔和|粉彩|鼠尾草|桃色)/i)) {
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
      if (profileHas(profile, /(?:bichromatic|monochrome|restrained|quiet|soft|pastel|克制|柔和)/i)) {
        add("restrained accent palette", 4);
      }
      if (profileHas(profile, /(?:multicolor|rainbow|chromatic|neon|多彩|高饱和)/i)) {
        add("multicolor palette conflicts with limited accents", -5);
      }
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
      theme.id === "playful"
      && preferences.wants_friendly
      && preferences.wants_lively
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
  selectionText,
};
