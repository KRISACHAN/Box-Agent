"""Offline regression tests for X-RACCOON agent header propagation.

The caller (e.g. officev3) passes its own session id via ACP ``_meta.session_id``.
Box-Agent forwards the session, turn, and title values to the gateway as
``X-RACCOON-*`` request headers. Empty values must not emit headers.

These tests stub the underlying SDK client so they run without network access
or a real config, asserting purely on the outbound request params.
"""

import pytest
import httpx
from openai import AsyncOpenAI

from box_agent.llm import AnthropicClient, OpenAIClient
from box_agent.llm.base import LLMClientBase
from box_agent.llm.llm_wrapper import LLMClient, LLMProvider
from box_agent.retry import RetryConfig
from box_agent.schema import Message

_HEADER = "X-RACCOON-Session-ID"
_TURN_HEADER = "X-RACCOON-Turn-ID"
_TITLE_HEADER = "X-RACCOON-Title"
# A normal (non-hosted-placeholder) key so _auth_headers passes the session
# header through untouched instead of swapping in bearer-token logic.
_API_KEY = "sk-test-not-a-placeholder"


class _FakeParsed:
    """Stand-in for a parsed SDK response; only ``content`` is read downstream."""

    content = "ok"
    thinking = None
    finish_reason = "stop"
    tool_calls: list = []
    usage = None


class _FakeRawResponse:
    request_id = "req-test"
    headers: dict = {}

    def parse(self):
        return _FakeParsed()


class _CapturingCreate:
    """Captures the kwargs of the last ``create(**params)`` call."""

    def __init__(self):
        self.last_params: dict | None = None

    def __call__(self, **params):
        self.last_params = params
        return _FakeRawResponse()


class _EmptyAsyncStream:
    response = type("_Response", (), {"headers": {}})()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _FakeRawStreamResponse:
    request_id = "req-stream-test"
    headers: dict = {}

    def parse(self):
        return _EmptyAsyncStream()


class _CapturingStreamCreate(_CapturingCreate):
    def __call__(self, **params):
        self.last_params = params
        return _FakeRawStreamResponse()


class _CapturingAnthropicStream(_CapturingCreate):
    def __call__(self, **params):
        self.last_params = params
        return _EmptyAsyncStream()


def _install_anthropic_fake(client: AnthropicClient) -> _CapturingCreate:
    cap = _CapturingCreate()

    class _WRR:
        create = staticmethod(cap)

    class _Messages:
        with_raw_response = _WRR()

    class _FakeSDK:
        messages = _Messages()

    client.client = _FakeSDK()
    return cap


def _install_anthropic_stream_fake(client: AnthropicClient) -> _CapturingCreate:
    cap = _CapturingAnthropicStream()

    class _Messages:
        stream = cap

    class _FakeSDK:
        messages = _Messages()

    client.client = _FakeSDK()
    return cap


def _install_openai_fake(client: OpenAIClient) -> _CapturingCreate:
    cap = _CapturingCreate()

    class _WRR:
        create = staticmethod(cap)

    class _Completions:
        with_raw_response = _WRR()

    class _Chat:
        completions = _Completions()

    class _FakeSDK:
        chat = _Chat()

    client.client = _FakeSDK()
    return cap


def _install_openai_stream_fake(client: OpenAIClient) -> _CapturingCreate:
    cap = _CapturingStreamCreate()

    class _WRR:
        create = staticmethod(cap)

    class _Completions:
        with_raw_response = _WRR()

    class _Chat:
        completions = _Completions()

    class _FakeSDK:
        chat = _Chat()

    client.client = _FakeSDK()
    return cap


async def _capture_generate(client, **kwargs) -> _CapturingCreate | None:
    """Call ``client.generate`` and capture outbound params.

    The header is injected into the request params *before* the SDK
    ``create()`` call, which is where ``_CapturingCreate`` records them. We
    don't feed a provider-correct fake response, so ``_parse_response`` may
    raise afterwards — that's irrelevant here, since the outbound request has
    already been captured. Swallow any post-capture error and assert on params.
    """
    try:
        await client.generate(**kwargs)
    except Exception:
        pass


async def _capture_stream(client, **kwargs) -> None:
    try:
        async for _event in client.generate_stream(**kwargs):
            pass
    except Exception:
        pass



# ── _session_header unit behavior ────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        ("sess-7-abc", {_HEADER: "sess-7-abc"}),
        ("  sess-trim  ", {_HEADER: "sess-trim"}),
        ("", {}),
        (None, {}),
    ],
)
def test_session_header_helper(value, expected):
    if value is None:
        assert LLMClientBase._session_header() == expected
    else:
        assert LLMClientBase._session_header(value) == expected


def test_agent_headers_emit_trimmed_non_empty_values():
    assert LLMClientBase._agent_headers(
        "  sess-7  ",
        "  sess-7-turn-1  ",
        "  Quarterly review  ",
    ) == {
        _HEADER: "sess-7",
        _TURN_HEADER: "sess-7-turn-1",
        _TITLE_HEADER: "Quarterly review",
    }


def test_agent_headers_omit_empty_values():
    assert LLMClientBase._agent_headers("", "  ", "") == {}


def test_agent_headers_encode_non_ascii_values_as_utf8_bytes():
    assert LLMClientBase._agent_headers(title="季度复盘") == {
        _TITLE_HEADER: "季度复盘".encode("utf-8")
    }


# ── Anthropic client ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_generate_emits_agent_headers():
    client = AnthropicClient(
        api_key=_API_KEY, api_base="https://api.anthropic.com", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_anthropic_fake(client)

    await _capture_generate(
        client,
        messages=[Message(role="user", content="hi")],
        session_id="sess-77",
        turn_id="sess-77-turn-1",
        title="Quarterly review",
    )

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers") == {
        _HEADER: "sess-77",
        _TURN_HEADER: "sess-77-turn-1",
        _TITLE_HEADER: "Quarterly review",
    }


@pytest.mark.asyncio
async def test_anthropic_generate_omits_header_when_empty():
    client = AnthropicClient(
        api_key=_API_KEY, api_base="https://api.anthropic.com", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_anthropic_fake(client)

    await _capture_generate(client, messages=[Message(role="user", content="hi")])

    assert cap.last_params is not None
    assert _HEADER not in cap.last_params.get("extra_headers", {})


@pytest.mark.asyncio
async def test_anthropic_stream_emits_agent_headers():
    client = AnthropicClient(
        api_key=_API_KEY,
        api_base="https://api.anthropic.com",
        model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_anthropic_stream_fake(client)

    await _capture_stream(
        client,
        messages=[Message(role="user", content="hi")],
        session_id="sess-stream",
        turn_id="sess-stream-turn-1",
        title="Quarterly review",
    )

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers") == {
        _HEADER: "sess-stream",
        _TURN_HEADER: "sess-stream-turn-1",
        _TITLE_HEADER: "Quarterly review",
    }


# ── OpenAI client ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openai_generate_emits_agent_headers():
    client = OpenAIClient(
        api_key=_API_KEY, api_base="https://api.example.com/v1", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_openai_fake(client)

    await _capture_generate(
        client,
        messages=[Message(role="user", content="hi")],
        session_id="sess-88",
        turn_id="sess-88-turn-1",
        title="Quarterly review",
    )

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers") == {
        _HEADER: "sess-88",
        _TURN_HEADER: "sess-88-turn-1",
        _TITLE_HEADER: "Quarterly review",
    }


@pytest.mark.asyncio
async def test_openai_generate_omits_header_when_empty():
    client = OpenAIClient(
        api_key=_API_KEY, api_base="https://api.example.com/v1", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_openai_fake(client)

    await _capture_generate(client, messages=[Message(role="user", content="hi")])

    assert cap.last_params is not None
    assert _HEADER not in cap.last_params.get("extra_headers", {})


@pytest.mark.asyncio
async def test_openai_stream_emits_agent_headers():
    client = OpenAIClient(
        api_key=_API_KEY,
        api_base="https://api.example.com/v1",
        model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_openai_stream_fake(client)

    await _capture_stream(
        client,
        messages=[Message(role="user", content="hi")],
        session_id="sess-stream",
        turn_id="sess-stream-turn-1",
        title="Quarterly review",
    )

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers") == {
        _HEADER: "sess-stream",
        _TURN_HEADER: "sess-stream-turn-1",
        _TITLE_HEADER: "Quarterly review",
    }


@pytest.mark.asyncio
async def test_openai_sdk_sends_utf8_title_without_header_encoding_failure():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["title"] = dict(request.headers.raw)[b"X-RACCOON-Title"]
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAIClient(
        api_key=_API_KEY,
        api_base="https://api.example.com/v1",
        model="m",
        retry_config=RetryConfig(enabled=False),
    )
    await client.client.close()
    client.client = AsyncOpenAI(
        api_key=_API_KEY,
        base_url=client.api_base,
        http_client=http_client,
    )
    try:
        await client.generate(
            messages=[Message(role="user", content="hi")],
            session_id="sess-utf8",
            turn_id="sess-utf8-turn-1",
            title="季度复盘",
        )
    finally:
        await client.client.close()

    assert captured["title"] == "季度复盘".encode("utf-8")


# ── Wrapper threads agent metadata through ───────────────────────────────────


@pytest.mark.asyncio
async def test_wrapper_threads_agent_headers_to_client():
    wrapper = LLMClient(
        api_key=_API_KEY, provider=LLMProvider.ANTHROPIC,
        api_base="https://api.anthropic.com", model="m",
        retry_config=RetryConfig(enabled=False),
    )
    cap = _install_anthropic_fake(wrapper._client)

    await _capture_generate(
        wrapper,
        messages=[Message(role="user", content="hi")],
        session_id="sess-wrap",
        turn_id="sess-wrap-turn-1",
        title="Quarterly review",
    )

    assert cap.last_params is not None
    assert cap.last_params.get("extra_headers") == {
        _HEADER: "sess-wrap",
        _TURN_HEADER: "sess-wrap-turn-1",
        _TITLE_HEADER: "Quarterly review",
    }
