"""Current-page browser intent guards shared by ACP and CLI turns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from box_agent.schema import Message


_CURRENT_PAGE_ONLY_TOOLS = frozenset(
    {
        "browser_read_current_page",
        "browser_connector_snapshot",
        "browser_connector_click",
        "browser_connector_fill",
        "browser_connector_submit",
    }
)
_OPTIONAL_URL_CURRENT_PAGE_TOOLS = frozenset(
    {
        "browser_read_page",
        "browser_read_article",
    }
)
_BROWSER_CONTEXT_TOOLS = frozenset(
    {
        "browser_open_url",
        "browser_read_page",
        "browser_read_article",
        "browser_read_current_page",
        "browser_connector_snapshot",
        "browser_connector_click",
        "browser_connector_fill",
        "browser_connector_submit",
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


def has_recent_successful_browser_context(messages: Sequence[Message]) -> bool:
    """Return whether the immediately prior turn completed a browser-context tool."""
    user_indices = [index for index, message in enumerate(messages) if message.role == "user"]
    if len(user_indices) < 2:
        return False

    previous_turn = messages[user_indices[-2] + 1 : user_indices[-1]]
    for message in reversed(previous_turn):
        if message.role != "tool" or message.name not in _BROWSER_CONTEXT_TOOLS:
            continue
        content = message.content if isinstance(message.content, str) else str(message.content)
        if not content.lstrip().startswith("Error:"):
            return True
    return False


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
    """Filter and validate tools that access the user's active browser tab."""

    allow_current_page: bool

    @classmethod
    def for_turn(
        cls,
        *,
        current_turn_text: str | None,
        messages: Sequence[Message],
    ) -> "BrowserToolIntentPolicy":
        user_text = current_turn_text if current_turn_text is not None else _latest_user_text(messages)
        allow_current_page = has_explicit_current_page_intent(user_text) or (
            is_browser_continuation(user_text)
            and has_recent_successful_browser_context(messages)
        )
        return cls(allow_current_page=allow_current_page)

    def is_tool_visible(self, tool_name: str) -> bool:
        """Hide current-tab-only tools unless the current turn explicitly needs them."""
        return self.allow_current_page or tool_name not in _CURRENT_PAGE_ONLY_TOOLS

    def tool_call_error(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        """Return an internal denial reason for a disallowed current-page call."""
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
