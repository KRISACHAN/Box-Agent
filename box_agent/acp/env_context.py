"""Environment-context injection for ACP sessions.

The Electron host knows things the runtime cannot easily probe — bundled
CLI paths (lark-cli, wecom-cli, dingtalk-cli), whether the browser-tools
shortcut has been completed, the user's platform. Hosts pass this through
``session/new._meta.env_context`` so the model stops claiming "you don't
have lark-cli installed" when in fact a bundled binary is sitting at a
known path.

The input is sanitized before it touches the system prompt:

* CLI paths must be absolute, free of control characters/backticks, and
  capped at ``_MAX_PATH_LEN`` chars. Violating entries are dropped.
* ``platform`` must match a conservative ``[A-Za-z0-9_-]`` charset and be
  ``<= _MAX_PLATFORM_LEN`` chars; violating values are discarded.
* Unknown top-level keys are still parsed into ``extras`` (so hosts can
  experiment without coordinating a backend bump) but are **not rendered
  into the system prompt**. They surface in logs only.

The trust model is "local stdio host" — we accept the host's facts but
defend against developer mistakes (accidental secrets in ``extras``,
malformed CLI paths) and accidental prompt-channel pollution (newlines
forging headings, backticks escaping fences).

This module deliberately does **not** consult ``action_hints``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

_KNOWN_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "cli",
        "platform",
        "browser_tools",
        "browser_connector",
        "image_service",
        "memory_configured",
        "runtimes",
        "obsidian",
    }
)

_MAX_PATH_LEN = 512
_MAX_NAME_LEN = 64
_MAX_PLATFORM_LEN = 32
_PLATFORM_ALLOWED_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def _has_unsafe_chars(value: str) -> bool:
    """True if string contains control chars, backticks, or markdown fence chars."""
    if "`" in value:
        return True
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def _is_absolute_path(value: str) -> bool:
    # Accept POSIX absolute paths; tolerate Windows ``C:\...`` style.
    return value.startswith("/") or (len(value) >= 3 and value[1:3] == ":\\")


def _sanitize_path(owner: str, raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        logger.warning("env_context.%s: drop — value is %s, not str/null", owner, type(raw).__name__)
        return None
    if len(raw) > _MAX_PATH_LEN:
        logger.warning("env_context.%s: drop — path exceeds %d chars", owner, _MAX_PATH_LEN)
        return None
    if _has_unsafe_chars(raw):
        logger.warning("env_context.%s: drop — unsafe chars in path", owner)
        return None
    if not _is_absolute_path(raw):
        logger.warning("env_context.%s: drop — path %r is not absolute", owner, raw)
        return None
    return raw


def _sanitize_cli(raw: Any) -> dict[str, str | None]:
    """Filter the cli mapping. Returns only entries that pass validation.

    Drops (with a warning log) any entry whose name has unsafe chars / is
    too long, or whose value is non-null but is not an absolute path /
    contains unsafe chars / exceeds the length cap.
    """
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, str | None] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not name or len(name) > _MAX_NAME_LEN:
            logger.warning("env_context.cli: drop entry with invalid name %r", name)
            continue
        if _has_unsafe_chars(name):
            logger.warning("env_context.cli: drop entry %r — unsafe chars in name", name)
            continue

        if value is None:
            cleaned[name] = None
            continue
        path = _sanitize_path(f"cli[{name}]", value)
        if path is not None:
            cleaned[name] = path
    return cleaned


def _sanitize_platform(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    if not raw or len(raw) > _MAX_PLATFORM_LEN:
        logger.warning("env_context.platform: drop — length %d", len(raw))
        return None
    if not all(ch in _PLATFORM_ALLOWED_CHARS for ch in raw):
        logger.warning("env_context.platform: drop — disallowed chars in %r", raw)
        return None
    return raw


def _sanitize_provider(raw: Any) -> str | None:
    if raw is None or not isinstance(raw, str):
        return None
    if not raw or len(raw) > _MAX_NAME_LEN:
        return None
    if _has_unsafe_chars(raw):
        return None
    if not all(ch in _PLATFORM_ALLOWED_CHARS for ch in raw):
        return None
    return raw


def _sanitize_label(raw: Any, *, max_len: int = _MAX_NAME_LEN) -> str | None:
    if raw is None or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw or len(raw) > max_len:
        return None
    if _has_unsafe_chars(raw):
        return None
    return raw


def _sanitize_runtimes(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}

    allowed_runtime_fields = {
        "python": ("path", "shell_path", "sandbox_path", "ready", "provider"),
        "node": ("path", "npm", "npx", "node_modules", "ready", "provider"),
    }
    path_fields = {"path", "shell_path", "sandbox_path", "npm", "npx", "node_modules"}
    cleaned: dict[str, dict[str, Any]] = {}

    for kind, value in raw.items():
        if kind not in allowed_runtime_fields or not isinstance(value, dict):
            logger.warning("env_context.runtimes: drop unsupported runtime %r", kind)
            continue

        runtime: dict[str, Any] = {}
        for field_name in allowed_runtime_fields[kind]:
            if field_name not in value:
                continue
            field_value = value[field_name]
            if field_name in path_fields:
                path = _sanitize_path(f"runtimes.{kind}.{field_name}", field_value)
                if path is not None:
                    runtime[field_name] = path
            elif field_name == "ready":
                if isinstance(field_value, bool):
                    runtime[field_name] = field_value
            elif field_name == "provider":
                provider = _sanitize_provider(field_value)
                if provider is not None:
                    runtime[field_name] = provider

        if runtime:
            cleaned[kind] = runtime
    return cleaned


def _sanitize_obsidian(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, Any] = {}
    for field_name in ("enabled", "cli_available", "app_running"):
        value = raw.get(field_name)
        if isinstance(value, bool):
            cleaned[field_name] = value

    vault_name = _sanitize_label(raw.get("vault_name"))
    if vault_name is not None:
        cleaned["vault_name"] = vault_name

    for field_name in ("vault_path", "cli_path", "app_path"):
        value = raw.get(field_name)
        if value is None:
            continue
        path = _sanitize_path(f"obsidian.{field_name}", value)
        if path is not None:
            cleaned[field_name] = path

    return cleaned


class BrowserToolsState(BaseModel):
    """Whether host-side browser tooling is installed/enabled.

    ``installed`` and ``enabled`` are independent: the user may have
    installed Chromium but kept the MCP entry disabled.
    """

    model_config = ConfigDict(extra="allow")

    installed: bool | None = None
    enabled: bool | None = None
    available: bool | None = None


class BrowserConnectorState(BaseModel):
    """Whether the real-browser connector extension is usable.

    The connector is a read-only enhancement for the user's real browser
    context. It is separate from Playwright automation: an enabled gateway is
    not enough if the extension is not connected or is paused.
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool | None = None
    connected: bool | None = None
    paused: bool | None = None
    available: bool | None = None


class ImageServiceState(BaseModel):
    """Whether the host-side image generation service is reachable.

    ``available`` signals that the model may call ``generate_image`` and
    expect a usable bitmap back. Hosts that have not wired up an image
    backend should pass ``available=False`` so the model falls back to
    HTML/CSS/icons instead of planning unreachable generate calls.
    """

    model_config = ConfigDict(extra="allow")

    available: bool | None = None


class HostRuntime(BaseModel):
    """Sanitized host-provided runtime metadata."""

    model_config = ConfigDict(extra="ignore")

    path: str | None = None
    shell_path: str | None = None
    sandbox_path: str | None = None
    npm: str | None = None
    npx: str | None = None
    node_modules: str | None = None
    ready: bool | None = None
    provider: str | None = None


class ObsidianState(BaseModel):
    """Sanitized host-provided Obsidian integration metadata."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool | None = None
    vault_path: str | None = None
    vault_name: str | None = None
    cli_path: str | None = None
    app_path: str | None = None
    cli_available: bool | None = None
    app_running: bool | None = None


class EnvContext(BaseModel):
    """Parsed view of ``session/new._meta.env_context``.

    Unknown top-level keys land in ``extras`` (logged only — not rendered
    into the system prompt, see :func:`build_env_context_prompt`). Known
    fields are typed and sanitized; anything that fails validation is
    discarded with a warning rather than rejecting the whole session.
    """

    model_config = ConfigDict(extra="ignore")

    cli: dict[str, str | None] = Field(default_factory=dict)
    platform: str | None = None
    browser_tools: BrowserToolsState | None = None
    browser_connector: BrowserConnectorState | None = None
    image_service: ImageServiceState | None = None
    memory_configured: bool | None = None
    runtimes: dict[str, HostRuntime] = Field(default_factory=dict)
    obsidian: ObsidianState | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_meta(cls, raw: Any) -> "EnvContext | None":
        """Parse ``_meta.env_context``. Returns ``None`` for missing/invalid input."""
        if raw is None:
            return None
        if not isinstance(raw, dict):
            logger.warning("env_context must be an object, got %s", type(raw).__name__)
            return None

        known: dict[str, Any] = {}
        extras: dict[str, Any] = {}
        for key, value in raw.items():
            if key in _KNOWN_TOP_LEVEL_KEYS:
                known[key] = value
            else:
                extras[key] = value
                logger.info("env_context: passthrough unknown key %s (not rendered into prompt)", key)

        # Sanitize known fields up-front so prompt renderer can trust them.
        if "cli" in known:
            known["cli"] = _sanitize_cli(known["cli"])
        if "platform" in known:
            known["platform"] = _sanitize_platform(known["platform"])
        if "runtimes" in known:
            known["runtimes"] = _sanitize_runtimes(known["runtimes"])
        if "obsidian" in known:
            known["obsidian"] = _sanitize_obsidian(known["obsidian"])

        try:
            ctx = cls.model_validate(known)
        except Exception as exc:
            logger.warning("env_context validation failed: %s", exc)
            return None
        ctx.extras = extras
        return ctx

    def is_empty(self) -> bool:
        """Empty iff nothing the prompt cares about. ``extras`` doesn't count."""
        return not (
            self.cli
            or self.platform
            or self.browser_tools is not None
            or self.browser_connector is not None
            or self.image_service is not None
            or self.memory_configured is not None
            or self.obsidian is not None
        )


def _format_cli_section(cli: dict[str, str | None]) -> list[str]:
    if not cli:
        return []
    available: list[str] = []
    missing: list[str] = []
    for name, path in sorted(cli.items()):
        if path:
            available.append(f"  - `{name}`: `{path}`")
        else:
            missing.append(f"`{name}`")
    lines: list[str] = []
    if available:
        lines.append("- 可用 CLI（机器上已安装，可以通过 bash 工具直接调用）：")
        lines.extend(available)
        if cli.get("lark-cli"):
            lines.append(
                "- 飞书/Lark CLI 策略：officev3 本地会话只允许用户身份；业务命令必须显式加 "
                "`--as user`，不要使用 `--as bot`、`config bind --identity bot-only` 或 "
                "`config strict-mode`。"
            )
    if missing:
        lines.append("- 未安装 CLI（不要假装能调用）：" + ", ".join(missing))
    return lines


def _format_browser_tools(state: BrowserToolsState) -> list[str]:
    if state.installed is None and state.enabled is None and state.available is None:
        return []
    parts = []
    if state.installed is not None:
        parts.append(f"installed={str(state.installed).lower()}")
    if state.enabled is not None:
        parts.append(f"enabled={str(state.enabled).lower()}")
    if state.available is not None:
        parts.append(f"available={str(state.available).lower()}")
    return [f"- 浏览器工具状态：{', '.join(parts)}"]


def _format_browser_connector(state: BrowserConnectorState) -> list[str]:
    if (
        state.enabled is None
        and state.connected is None
        and state.paused is None
        and state.available is None
    ):
        return []
    parts = []
    if state.enabled is not None:
        parts.append(f"enabled={str(state.enabled).lower()}")
    if state.connected is not None:
        parts.append(f"connected={str(state.connected).lower()}")
    if state.paused is not None:
        parts.append(f"paused={str(state.paused).lower()}")
    if state.available is not None:
        parts.append(f"available={str(state.available).lower()}")
    return [f"- 真实浏览器连接器状态：{', '.join(parts)}"]


def _state_available(value: bool | None, fallback: bool) -> bool:
    return value if value is not None else fallback


def _format_browser_capability_policy(
    browser_tools: BrowserToolsState | None,
    browser_connector: BrowserConnectorState | None,
) -> list[str]:
    if browser_tools is None and browser_connector is None:
        return []

    playwright_available = False
    if browser_tools is not None:
        fallback = bool(browser_tools.enabled and browser_tools.installed)
        playwright_available = _state_available(browser_tools.available, fallback)

    connector_available = False
    if browser_connector is not None:
        fallback = bool(
            browser_connector.enabled
            and browser_connector.connected
            and browser_connector.paused is not True
        )
        connector_available = _state_available(browser_connector.available, fallback)

    lines = [
        "- 浏览器能力策略：Playwright 是基础网页能力，真实浏览器连接器是读取用户真实浏览器上下文的增强能力。"
    ]
    if playwright_available and connector_available:
        lines.append(
            "  - 两者都可用：普通公开网页、后台打开、点击、填写、截图、页面结构/网络检查等自动化任务优先使用 Playwright；"
            "当前页、用户已登录页面、内网页、公众号等需要真实浏览器上下文的只读任务优先使用连接器。"
        )
    elif playwright_available:
        lines.append(
            "  - 当前只有 Playwright 可用或连接器未连接：凡是 Playwright 能完成的网页任务必须使用 Playwright；"
            "不要因为连接器更适合而要求用户先安装或连接插件。"
        )
    elif connector_available:
        lines.append(
            "  - 当前只有真实浏览器连接器可用：可用于只读读取当前页或链接；需要点击、填写、截图、自动化时提示用户启用 Playwright。"
        )
    else:
        lines.append(
            "  - 当前两类浏览器能力都不可用：优先引导用户启用 Playwright 浏览器工具；"
            "连接器只作为当前页、登录态页面、内网页读取的增强项。"
        )
    lines.append(
        "  - 如果连接器工具返回 `extension_not_connected`，且 Playwright 可用且任务有普通公开 URL，改用 Playwright；"
        "不要把插件未连接作为普通网页任务的终点。"
    )
    return lines


def _format_image_service(state: ImageServiceState) -> list[str]:
    if state.available is None:
        return []
    label = "可用（可调用 generate_image）" if state.available else "不可用（不要计划调用 generate_image，请改用 HTML/CSS/图标）"
    return [f"- 生图服务状态：{label}"]


def _format_obsidian(state: ObsidianState) -> list[str]:
    parts: list[str] = []
    if state.enabled is not None:
        parts.append(f"enabled={str(state.enabled).lower()}")
    if state.cli_available is not None:
        parts.append(f"cli_available={str(state.cli_available).lower()}")
    if state.app_running is not None:
        parts.append(f"app_running={str(state.app_running).lower()}")

    lines: list[str] = []
    if parts:
        lines.append(f"- Obsidian 状态：{', '.join(parts)}")
    if state.vault_name:
        lines.append(f"  - Vault：{state.vault_name}")
    if state.vault_path:
        lines.append(f"  - Vault 路径：`{state.vault_path}`")
    if state.cli_path:
        lines.append(f"  - Obsidian CLI：`{state.cli_path}`")
    if state.app_path:
        lines.append(f"  - Obsidian App：`{state.app_path}`")
    if state.enabled is True:
        lines.append(
            "- Obsidian 写入/打开策略：当用户要求导出、写入、保存或追加到 Obsidian 时，"
            "必须优先使用 `obsidian_create_note`、`obsidian_update_note` 或 `obsidian_daily_note`；"
            "不要用 bash 直接调用 `obsidian create/append/prepend/open/daily`。"
            "如果 prompt 中存在 `obsidian_context`，且用户要求修改该引用笔记，"
            "必须使用 context 里的 Vault 相对 `path` 调用 `obsidian_update_note`；"
            "不要修改 workspace 副本或 `.data-sources` 文件。"
        )
    return lines


def build_env_context_prompt(ctx: EnvContext | None) -> str:
    """Render ``EnvContext`` into a markdown checklist for the system prompt.

    Only sanitized known fields go in. ``extras`` is intentionally
    excluded: passthrough values must not be promoted into the model's
    high-priority context without explicit backend support.
    """
    if ctx is None or ctx.is_empty():
        return ""

    lines: list[str] = ["## 当前用户环境", ""]
    if ctx.platform:
        lines.append(f"- 操作系统：`{ctx.platform}`")
    lines.extend(_format_cli_section(ctx.cli))
    if ctx.browser_tools is not None:
        lines.extend(_format_browser_tools(ctx.browser_tools))
    if ctx.browser_connector is not None:
        lines.extend(_format_browser_connector(ctx.browser_connector))
    lines.extend(_format_browser_capability_policy(ctx.browser_tools, ctx.browser_connector))
    if ctx.image_service is not None:
        lines.extend(_format_image_service(ctx.image_service))
    if ctx.obsidian is not None:
        lines.extend(_format_obsidian(ctx.obsidian))
    if ctx.memory_configured is not None:
        state = "已完成" if ctx.memory_configured else "未完成"
        lines.append(f"- 个人记忆配置：{state}")

    lines.append("")
    lines.append(
        "请把以上信息当作事实依据：不要否认已列出可用的工具，也不要假装能调用未列出的工具。"
        "如果用户的需求需要某个未安装的工具，明确告知并建议安装途径。"
    )
    return "\n".join(lines)
