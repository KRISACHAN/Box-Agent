"""LLM client wrapper that supports multiple providers.

This module provides a unified interface for different LLM providers
(Anthropic and OpenAI) through a single LLMClient class.
"""

import logging
from collections.abc import AsyncIterator
from copy import copy

from ..retry import RetryConfig
from ..schema import LLMProvider, LLMResponse, Message, StreamEvent
from .anthropic_client import AnthropicClient
from .base import LLMClientBase
from .openai_client import OpenAIClient
from .think_tag_splitter import split_inline_think, unwrap_think_tags
from .token_meter import record_usage

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM Client wrapper supporting multiple providers.

    This class provides a unified interface for different LLM providers
    (Anthropic and OpenAI). It automatically instantiates the correct
    underlying client based on the provider parameter.
    """

    def __init__(
        self,
        api_key: str,
        provider: LLMProvider = LLMProvider.ANTHROPIC,
        api_base: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-20250514",
        retry_config: RetryConfig | None = None,
        max_output_tokens: int = 64000,
        auth_token: str = "",
        auth_file: str = "",
        timeout: float = 600.0,
    ):
        """Initialize LLM client with specified provider.

        Args:
            api_key: API key for authentication
            provider: LLM provider (anthropic or openai)
            api_base: Base URL for the API
            model: Model name to use
            retry_config: Optional retry configuration
            max_output_tokens: Per-request output token cap forwarded to the
                underlying provider as ``max_tokens``.
            auth_token: Optional in-memory product login token.
            auth_file: Optional auth.json path read before every request.
            timeout: Wall-clock cap (seconds) handed to the provider SDK.
        """
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.retry_config = retry_config or RetryConfig()
        self.max_output_tokens = max_output_tokens
        self.auth_token = auth_token
        self.auth_file = auth_file
        self.timeout = timeout

        # Normalize api_base (remove trailing slash)
        api_base = api_base.rstrip("/")
        self.api_base = api_base

        # Instantiate the appropriate client
        self._client: LLMClientBase
        if provider == LLMProvider.ANTHROPIC:
            self._client = AnthropicClient(
                api_key=api_key,
                api_base=api_base,
                model=model,
                retry_config=retry_config,
                max_output_tokens=max_output_tokens,
                auth_token=auth_token,
                auth_file=auth_file,
                timeout=timeout,
            )
        elif provider == LLMProvider.OPENAI:
            self._client = OpenAIClient(
                api_key=api_key,
                api_base=api_base,
                model=model,
                retry_config=retry_config,
                max_output_tokens=max_output_tokens,
                auth_token=auth_token,
                auth_file=auth_file,
                timeout=timeout,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        logger.info("Initialized LLM client with provider: %s, api_base: %s", provider, api_base)

    def for_model(self, model: str) -> "LLMClient":
        """Return a client with the same endpoint/auth settings for ``model``.

        ACP conversation sessions use this to bind an app-owned session to a
        hosted catalog model without mutating the process-wide default client.
        """
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("model must not be empty")

        # The provider wrapper owns per-request mutable state (for example a
        # one-shot max-token override), while the underlying SDK transport is
        # safe to share. Shallow-copy both wrappers so sessions stay isolated
        # without creating an unbounded set of HTTP connection pools.
        client = copy(self)
        client._client = copy(self._client)
        client.model = normalized_model
        client._client.model = normalized_model
        if hasattr(client._client, "_ephemeral_max_output_tokens"):
            client._client._ephemeral_max_output_tokens = None
        return client

    @property
    def retry_callback(self):
        """Get retry callback."""
        return self._client.retry_callback

    @retry_callback.setter
    def retry_callback(self, value):
        """Set retry callback."""
        self._client.retry_callback = value

    async def generate(
        self,
        messages: list[Message],
        tools: list | None = None,
        *,
        thinking_enabled: bool = False,
        session_id: str = "",
        turn_id: str = "",
        title: str = "Box-Agent",
        call_kind: str = "",
    ) -> LLMResponse:
        """Generate response from LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts
            thinking_enabled: Enable provider-native extended thinking.
            session_id: Optional caller-owned session id.
            turn_id: Optional caller-owned turn id.
            title: Optional trace title.

        Returns:
            LLMResponse containing the generated content
        """
        response = await self._client.generate(
            messages,
            tools,
            thinking_enabled=thinking_enabled,
            session_id=session_id,
            turn_id=turn_id,
            title=title,
            call_kind=call_kind,
        )
        record_usage(response.usage)
        if response.content and "<think>" in response.content:
            cleaned, extracted = split_inline_think(response.content)
            if extracted:
                merged_thinking = (response.thinking or "") + extracted
                response = response.model_copy(update={"content": cleaned, "thinking": merged_thinking})
        return response

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list | None = None,
        *,
        thinking_enabled: bool = False,
        session_id: str = "",
        turn_id: str = "",
        title: str = "Box-Agent",
        call_kind: str = "",
    ) -> AsyncIterator[StreamEvent]:
        """Generate streaming response from LLM.

        Yields StreamEvent chunks for thinking/text deltas as they arrive.
        The final event has type="finish" and carries tool_calls + usage.

        Args:
            messages: List of conversation messages
            tools: Optional list of Tool objects or dicts
            thinking_enabled: Enable provider-native extended thinking.
            session_id: Optional caller-owned session id.
            turn_id: Optional caller-owned turn id.
            title: Optional trace title.

        Yields:
            StreamEvent chunks
        """
        upstream = self._client.generate_stream(
            messages,
            tools,
            thinking_enabled=thinking_enabled,
            session_id=session_id,
            turn_id=turn_id,
            title=title,
            call_kind=call_kind,
        )
        async for event in unwrap_think_tags(upstream):
            if event.type == "finish":
                record_usage(event.usage)
            yield event


class SessionBoundLLM:
    """Stable per-session LLM reference with inherited request correlation."""

    def __init__(self, client: LLMClient):
        self._delegate = client
        self._session_id = ""
        self._turn_id = ""
        self._title = "Box-Agent"
        self._call_kind = ""

    def bind(self, client: LLMClient) -> None:
        self._delegate = client

    def set_request_context(
        self,
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
        title: str | None = None,
        call_kind: str | None = None,
    ) -> None:
        """Set defaults inherited by nested LLM calls in this ACP session."""

        if session_id is not None:
            self._session_id = session_id.strip()
        if turn_id is not None:
            self._turn_id = turn_id.strip()
        if title is not None:
            self._title = title.strip() or "Box-Agent"
        if call_kind is not None:
            self._call_kind = call_kind.strip()

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    async def generate(
        self,
        messages: list[Message],
        tools: list | None = None,
        *,
        thinking_enabled: bool = False,
        session_id: str = "",
        turn_id: str = "",
        title: str = "",
        call_kind: str = "",
    ) -> LLMResponse:
        client = self._delegate
        kwargs = {
            "thinking_enabled": thinking_enabled,
            "session_id": session_id.strip() or self._session_id,
            "turn_id": turn_id.strip() or self._turn_id,
            "title": title.strip() or self._title,
        }
        effective_call_kind = call_kind.strip() or self._call_kind
        if effective_call_kind:
            kwargs["call_kind"] = effective_call_kind
        return await client.generate(messages, tools, **kwargs)

    async def generate_stream(
        self,
        messages: list[Message],
        tools: list | None = None,
        *,
        thinking_enabled: bool = False,
        session_id: str = "",
        turn_id: str = "",
        title: str = "",
        call_kind: str = "",
    ) -> AsyncIterator[StreamEvent]:
        client = self._delegate
        kwargs = {
            "thinking_enabled": thinking_enabled,
            "session_id": session_id.strip() or self._session_id,
            "turn_id": turn_id.strip() or self._turn_id,
            "title": title.strip() or self._title,
        }
        effective_call_kind = call_kind.strip() or self._call_kind
        if effective_call_kind:
            kwargs["call_kind"] = effective_call_kind
        async for event in client.generate_stream(messages, tools, **kwargs):
            yield event
