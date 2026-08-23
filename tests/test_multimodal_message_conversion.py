"""Provider adapter tests for canonical multimodal input blocks."""

import pytest

from box_agent.llm import AnthropicClient, OpenAIClient
from box_agent.schema import Message


def _message() -> Message:
    return Message(
        role="user",
        content=[
            {"type": "text", "text": "Inspect image 1."},
            {"type": "input_image", "media_type": "image/png", "data": "YWJj"},
        ],
    )


def test_anthropic_adapter_converts_canonical_image_block():
    client = AnthropicClient(api_key="test", api_base="https://example.test", model="m")

    _system, messages = client._convert_messages([_message()])

    assert messages[0]["content"][1] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "YWJj",
        },
    }


def test_anthropic_adapter_merges_tool_result_with_transient_image_user_turn():
    client = AnthropicClient(api_key="test", api_base="https://example.test", model="m")
    messages = [
        Message(
            role="tool",
            content="image attached transiently",
            tool_call_id="image-1",
            name="inspect_images",
        ),
        _message(),
    ]

    _system, converted = client._convert_messages(messages)

    assert len(converted) == 1
    assert converted[0]["role"] == "user"
    assert [block["type"] for block in converted[0]["content"]] == [
        "tool_result",
        "text",
        "image",
    ]


def test_openai_adapter_converts_canonical_image_block():
    client = OpenAIClient(api_key="test", api_base="https://example.test", model="m")

    _system, messages = client._convert_messages([_message()])

    assert messages[0]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,YWJj"},
    }


@pytest.mark.parametrize("client_class", [AnthropicClient, OpenAIClient])
def test_provider_adapter_rejects_malformed_canonical_image_block(client_class):
    client = client_class(api_key="test", api_base="https://example.test", model="m")
    message = Message(
        role="user",
        content=[{"type": "input_image", "media_type": "image/gif", "data": ""}],
    )

    with pytest.raises(ValueError, match="invalid canonical input_image block"):
        client._convert_messages([message])
