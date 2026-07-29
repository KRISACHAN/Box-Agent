"""Browser backend routing and current-page guards shared by ACP and CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from box_agent.schema import Message


BrowserBackend = Literal["auto", "playwright", "browser_connector"]

_CURRENT_PAGE_ONLY_TOOLS = frozenset(
    {
        "browser_read_current_page",
        "browser_connector_snapshot",
        "browser_connector_click",
        "browser_connector_fill",
        "browser_connector_submit",
    }
)
_BROWSER_GATEWAY_TOOLS = frozenset(
    {
        "browser_open_url",
        "browser_read_page",
        "browser_read_article",
        "browser_read_current_page",
        "browser_read_section",
        "browser_extract_structured_data",
        "browser_connector_snapshot",
        "browser_connector_click",
        "browser_connector_fill",
        "browser_connector_submit",
        "browser_session_start",
        "browser_session_call",
        "browser_session_end",
    }
)
_OPTIONAL_URL_CURRENT_PAGE_TOOLS = frozenset(
    {
        "browser_read_page",
        "browser_read_article",
    }
)
_CURRENT_PAGE_REFERENCE_RE = re.compile(
    r"(?:"
    r"当前(?:页|页面|网页|标签页)"
    r"|(?:这个|此|本)(?:页面|网页|标签页)"
    r"|(?:我的|我现在的)?浏览器(?:里|中|当前)(?:打开的)?(?:页面|网页|标签页)?"
    r"|我(?:现在)?(?:打开|正在看)的(?:页面|网页|标签页)"
    r"|(?:我)?(?:已经|已)?登录(?:后(?:的)?|着|的)?(?:页面|网页|网站)"
    r"|(?:这篇|当前|这个)公众号(?:文章|页面)?"
    r"|current\s+(?:browser\s+)?(?:page|tab)"
    r"|this\s+(?:browser\s+)?(?:page|tab)"
    r"|(?:page|tab)\s+i(?:'|’)m\s+(?:currently\s+)?(?:viewing|on)"
    r"|(?:page|tab)\s+i\s+have\s+open"
    r")",
    re.IGNORECASE,
)
_PLAYWRIGHT_EXPLICIT_RE = re.compile(
    r"(?:\bplaywright\b|无头浏览器|无头模式|\bheadless\b)",
    re.IGNORECASE,
)
_CONNECTOR_CONTEXT_RE = re.compile(
    r"(?:"
    r"真实浏览器|浏览器连接器|浏览器插件"
    r"|登录态|已经登录|已登录|登录后的?"
    r"|(?:当前|我的|现有|已有|保留|使用|依赖).{0,8}cookie"
    r"|cookie.{0,8}(?:登录|会话|状态)"
    r"|内网(?:页面|网站|系统|地址|链接|数据|后台)|公司内部网站"
    r"|公众号(?:文章|页面|链接)"
    r"|\bbrowser\s+connector\b|\breal\s+browser\b|\blogged[\s-]?in\b"
    r"|\b(?:existing|current|my)\s+cookies?\b|\bintranet\s+(?:page|site|system)\b"
    r")",
    re.IGNORECASE,
)
_PUBLIC_WEB_RETRIEVAL_RE = re.compile(
    r"(?:"
    r"检索|搜索|查找|查询|调研"
    r"|爬虫|爬取|抓取|采集|收集(?:网页|网站|公开资料|公开信息|数据)"
    r"|批量(?:读取|获取|整理|分析).{0,8}(?:网页|页面|网站|链接|数据)"
    r"|公开(?:网页|网站|页面|链接)"
    r"|\bsearch\b|\bresearch\b|\bcrawl(?:er|ing)?\b|\bscrap(?:e|er|ing)\b"
    r"|\bharvest\b|\bcollect\b.{0,20}\b(?:web|page|site|data)\b"
    r")",
    re.IGNORECASE,
)
_URL_BASED_READ_RE = re.compile(
    r"(?:"
    r"https?://"
    r"|(?:读取|总结|提取|分析|整理|打开).{0,12}(?:网页|页面|网站|链接|url)"
    r"|(?:read|summarize|extract|analy[sz]e|open).{0,20}\b(?:url|page|site|link)\b"
    r")",
    re.IGNORECASE,
)
_FORM_INTERACTION_RE = re.compile(
    r"(?:填表|填写|填好|填完|录入|表单|字段|\bfill(?:ing)?\b|\bform\b|\binput\b)",
    re.IGNORECASE,
)
_HUMAN_REVIEW_RE = re.compile(
    r"(?:"
    r"(?:让我|给我|由我|我来|用户|人工|手动|最后人|最后用户).{0,16}"
    r"(?:看|查看|检查|确认|审核|点击|提交|接管)"
    r"|(?:填好|填完|填写完成).{0,16}(?:让我|给我|由我|我来|用户|人工|手动|看着|查看|确认|提交)"
    r"|(?:看着|显示浏览器|打开浏览器给我看|不要关闭浏览器)"
    r"|\b(?:let\s+me|i(?:'|’)ll|user|human|manually)\b.{0,40}"
    r"\b(?:review|inspect|verify|confirm|click|submit|take\s+over)\b"
    r"|\bhand(?:\s|-)?off\b"
    r")",
    re.IGNORECASE,
)
_BROWSER_CONTINUATION_RE = re.compile(
    r"^\s*(?:"
    r"继续(?:看|往下看|分析|对比)?"
    r"|接着(?:看|分析|对比)?"
    r"|往下看"
    r"|再往下"
    r"|下一页"
    r"|翻页"
    r"|展开(?:一下)?"
    r"|再看(?:一下)?"
    r"|继续对比(?:一下)?"
    r"|(?:现在)?提交(?:吧|表单)?"
    r"|确认提交"
    r"|continue"
    r"|keep\s+going"
    r"|next\s+page"
    r")\s*[。.!！]?\s*$",
    re.IGNORECASE,
)
_CURRENT_PAGE_INTENT_ERROR = (
    "CURRENT_PAGE_INTENT_REQUIRED: the latest user request does not explicitly "
    "refer to the current browser page or continue a recent successful browser "
    "interaction. Do not inspect the user's active tab. Answer directly, use "
    "web_search, or use a URL-based browser tool instead."
)
_HEADLESS_BROWSER_REQUIRED_ERROR = (
    "BROWSER_BACKEND_MISMATCH: this turn is public web retrieval or crawling. "
    "Do not open or manipulate the user's real browser. Use web_search or the "
    "standalone headless Playwright MCP tools."
)
_REAL_BROWSER_REQUIRED_ERROR = (
    "BROWSER_BACKEND_MISMATCH: this turn requires the user's visible real "
    "browser for current login state or human review/handoff. Use Browser "
    "Connector tools and leave final submission to the user unless they "
    "explicitly authorize it."
)
_HUMAN_FINAL_ACTION_REQUIRED_ERROR = (
    "HUMAN_FINAL_ACTION_REQUIRED: the user asked to review, take over, or "
    "perform the final click themselves. Fill the visible real-browser form, "
    "stop before submission, and ask the user to review it."
)


def has_explicit_current_page_intent(user_text: str | None) -> bool:
    """Return whether the user explicitly refers to their current browser page."""
    if not user_text or not user_text.strip():
        return False
    return _CURRENT_PAGE_REFERENCE_RE.search(user_text.strip()) is not None


def is_browser_continuation(user_text: str | None) -> bool:
    """Return whether a short request continues the immediately prior browser task."""
    if not user_text or not user_text.strip():
        return False
    return _BROWSER_CONTINUATION_RE.fullmatch(user_text.strip()) is not None


def has_human_browser_handoff_intent(user_text: str | None) -> bool:
    """Return whether a visible browser must remain available for human review."""
    if not user_text or not user_text.strip():
        return False
    text = user_text.strip()
    return _HUMAN_REVIEW_RE.search(text) is not None and (
        _FORM_INTERACTION_RE.search(text) is not None
        or re.search(
            r"(?:浏览器|页面|网页|标签页|\bbrowser\b|\bpage\b)",
            text,
            re.IGNORECASE,
        )
        is not None
        or re.search(
            r"(?:最后人|最后用户|用户|人工|手动|我来).{0,16}(?:点击|提交|接管)",
            text,
            re.IGNORECASE,
        )
        is not None
    )


def classify_browser_backend_intent(user_text: str | None) -> BrowserBackend:
    """Choose the browser backend required by the current user request."""
    if not user_text or not user_text.strip():
        return "auto"
    text = user_text.strip()
    if (
        has_explicit_current_page_intent(text)
        or has_human_browser_handoff_intent(text)
        or _CONNECTOR_CONTEXT_RE.search(text) is not None
    ):
        return "browser_connector"
    if _PLAYWRIGHT_EXPLICIT_RE.search(text) is not None:
        return "playwright"
    if _FORM_INTERACTION_RE.search(text) is not None:
        return "playwright"
    if (
        _PUBLIC_WEB_RETRIEVAL_RE.search(text) is not None
        or _URL_BASED_READ_RE.search(text) is not None
    ):
        return "playwright"
    return "auto"


def _is_playwright_browser_tool(tool_name: str) -> bool:
    return tool_name.startswith("browser_") and tool_name not in _BROWSER_GATEWAY_TOOLS


def _recent_successful_browser_backend(
    messages: Sequence[Message],
) -> BrowserBackend:
    """Return the backend used successfully in the immediately prior turn."""
    user_indices = [index for index, message in enumerate(messages) if message.role == "user"]
    if len(user_indices) < 2:
        return "auto"

    previous_turn = messages[user_indices[-2] + 1 : user_indices[-1]]
    for message in reversed(previous_turn):
        if message.role != "tool" or not message.name:
            continue
        if (
            message.name not in _BROWSER_GATEWAY_TOOLS
            and not _is_playwright_browser_tool(message.name)
        ):
            continue
        content = message.content if isinstance(message.content, str) else str(message.content)
        if content.lstrip().startswith("Error:"):
            continue
        if message.name in _BROWSER_GATEWAY_TOOLS:
            return "browser_connector"
        if message.name and _is_playwright_browser_tool(message.name):
            return "playwright"
    return "auto"


def has_recent_successful_browser_context(messages: Sequence[Message]) -> bool:
    """Return whether the prior turn successfully used the real-browser context."""
    return _recent_successful_browser_backend(messages) == "browser_connector"


def _latest_user_text(messages: Sequence[Message]) -> str:
    for message in reversed(messages):
        if message.role != "user":
            continue
        if isinstance(message.content, str):
            return message.content
        return "\n".join(
            str(block.get("text", ""))
            for block in message.content
            if isinstance(block, dict)
        )
    return ""


@dataclass(frozen=True, slots=True)
class BrowserToolIntentPolicy:
    """Filter and validate browser tools according to the required backend."""

    allow_current_page: bool
    backend: BrowserBackend
    human_handoff: bool

    @classmethod
    def for_turn(
        cls,
        *,
        current_turn_text: str | None,
        messages: Sequence[Message],
    ) -> "BrowserToolIntentPolicy":
        user_text = current_turn_text if current_turn_text is not None else _latest_user_text(messages)
        continuation_backend: BrowserBackend = "auto"
        if is_browser_continuation(user_text):
            continuation_backend = _recent_successful_browser_backend(messages)
        backend = classify_browser_backend_intent(user_text)
        human_handoff = has_human_browser_handoff_intent(user_text)
        if backend == "auto":
            backend = continuation_backend
        allow_current_page = backend == "browser_connector" and (
            has_explicit_current_page_intent(user_text)
            or human_handoff
            or _CONNECTOR_CONTEXT_RE.search(user_text or "") is not None
            or continuation_backend == "browser_connector"
        )
        return cls(
            allow_current_page=allow_current_page,
            backend=backend,
            human_handoff=human_handoff,
        )

    def is_tool_visible(self, tool_name: str) -> bool:
        """Expose only the browser backend appropriate for the current turn."""
        if not self.allow_current_page and tool_name in _CURRENT_PAGE_ONLY_TOOLS:
            return False
        if self.human_handoff and tool_name == "browser_connector_submit":
            return False
        if self.backend == "playwright" and tool_name in _BROWSER_GATEWAY_TOOLS:
            return False
        if self.backend == "browser_connector" and _is_playwright_browser_tool(tool_name):
            return False
        return True

    def tool_call_error(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        """Return an internal denial reason for a disallowed browser call."""
        if self.human_handoff and tool_name == "browser_connector_submit":
            return _HUMAN_FINAL_ACTION_REQUIRED_ERROR
        if self.backend == "playwright" and tool_name in _BROWSER_GATEWAY_TOOLS:
            return _HEADLESS_BROWSER_REQUIRED_ERROR
        if self.backend == "browser_connector" and _is_playwright_browser_tool(tool_name):
            return _REAL_BROWSER_REQUIRED_ERROR
        if self.allow_current_page:
            return None
        if tool_name in _CURRENT_PAGE_ONLY_TOOLS:
            return _CURRENT_PAGE_INTENT_ERROR
        if tool_name in _OPTIONAL_URL_CURRENT_PAGE_TOOLS and not arguments.get("url"):
            return _CURRENT_PAGE_INTENT_ERROR
        if tool_name == "browser_session_call":
            action = str(arguments.get("action") or "")
            nested_args = arguments.get("args")
            if (
                action in {"read_page", "read_article"}
                and not isinstance(nested_args, dict)
            ):
                return _CURRENT_PAGE_INTENT_ERROR
            if (
                action in {"read_page", "read_article"}
                and isinstance(nested_args, dict)
                and not nested_args.get("url")
            ):
                return _CURRENT_PAGE_INTENT_ERROR
        return None
