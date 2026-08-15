"""Tests for the vision_review tool."""

from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path

import pytest

from box_agent.schema import LLMResponse
from box_agent.tools.setup import add_workspace_tools
from box_agent.tools.vision_review_tool import (
    _MAX_LONG_EDGE_PX,
    VisionReviewTool,
)


_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class FakeVisionLLM:
    provider = "openai"

    def __init__(self) -> None:
        self.messages = None
        self.tools = "unset"
        self.call_kind = None

    async def generate(self, messages, tools=None, *, thinking_enabled=False, call_kind=""):
        self.messages = messages
        self.tools = tools
        self.call_kind = call_kind
        return LLMResponse(
            content=(
                "# Visual Review\n\n"
                "## Summary\n- Overall: PASS\n- Reviewed images: 1\n\n"
                "## Per-page findings\n"
                "| Page | Source image | Status | Findings | Suggested fix |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| 1 | slide.png | PASS | Looks readable. | None |"
            ),
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_vision_review_reads_image_sends_image_content_and_writes_report(tmp_path: Path):
    image = tmp_path / "slide.png"
    image.write_bytes(_ONE_PIXEL_PNG)
    llm = FakeVisionLLM()
    tool = VisionReviewTool(llm=llm, workspace_dir=str(tmp_path), allow_full_access=False)

    result = await tool.execute(image_paths=["slide.png"])

    assert result.success, result.error
    assert llm.call_kind == "utility"
    report = tmp_path / "visual_review.md"
    assert report.exists()
    assert "Overall: PASS" in report.read_text()
    assert "Visual review written to visual_review.md" in result.content

    assert llm.tools is None
    assert llm.messages[1].role == "user"
    blocks = llm.messages[1].content
    assert any(block.get("type") == "image_url" for block in blocks)
    image_block = next(block for block in blocks if block.get("type") == "image_url")
    assert image_block["image_url"]["url"].startswith("data:image/png;base64,")
    assert "slide.png" in blocks[0]["text"]


@pytest.mark.asyncio
async def test_vision_review_default_report_follows_first_image_directory(tmp_path: Path):
    image_dir = tmp_path / "future_weather_deck" / "qa"
    image_dir.mkdir(parents=True)
    image = image_dir / "contact_sheet.png"
    image.write_bytes(_ONE_PIXEL_PNG)
    tool = VisionReviewTool(llm=FakeVisionLLM(), workspace_dir=str(tmp_path), allow_full_access=False)

    result = await tool.execute(image_paths=["future_weather_deck/qa/contact_sheet.png"])

    assert result.success, result.error
    assert (image_dir / "visual_review.md").exists()
    assert not (tmp_path / "qa" / "visual_review.md").exists()
    assert "Visual review written to future_weather_deck/qa/visual_review.md" in result.content


@pytest.mark.asyncio
async def test_vision_review_explicit_output_path_still_overrides_default(tmp_path: Path):
    image_dir = tmp_path / "future_weather_deck" / "qa"
    image_dir.mkdir(parents=True)
    image = image_dir / "contact_sheet.png"
    image.write_bytes(_ONE_PIXEL_PNG)
    tool = VisionReviewTool(llm=FakeVisionLLM(), workspace_dir=str(tmp_path), allow_full_access=False)

    result = await tool.execute(
        image_paths=["future_weather_deck/qa/contact_sheet.png"],
        output_path="qa/visual_review.md",
    )

    assert result.success, result.error
    assert (tmp_path / "qa" / "visual_review.md").exists()
    assert "Visual review written to qa/visual_review.md" in result.content


@pytest.mark.asyncio
async def test_vision_review_rejects_non_image_files(tmp_path: Path):
    text_file = tmp_path / "not-image.txt"
    text_file.write_text("not an image")
    tool = VisionReviewTool(llm=FakeVisionLLM(), workspace_dir=str(tmp_path), allow_full_access=False)

    result = await tool.execute(image_paths=["not-image.txt"])

    assert not result.success
    assert "Unsupported image type" in result.error


@pytest.mark.asyncio
async def test_vision_review_uses_anthropic_image_blocks(tmp_path: Path):
    image = tmp_path / "slide.jpg"
    image.write_bytes(b"fake jpeg bytes")
    llm = FakeVisionLLM()
    llm.provider = "anthropic"
    tool = VisionReviewTool(llm=llm, workspace_dir=str(tmp_path), allow_full_access=True)

    result = await tool.execute(image_paths=[str(image)])

    assert result.success, result.error
    blocks = llm.messages[1].content
    image_block = next(block for block in blocks if block.get("type") == "image")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/jpeg"
    assert image_block["source"]["data"] == base64.b64encode(b"fake jpeg bytes").decode("ascii")


@pytest.mark.asyncio
async def test_vision_review_downsamples_oversized_image(tmp_path: Path):
    """An image whose long edge exceeds the ceiling is resized before sending."""
    pytest.importorskip("PIL")
    from PIL import Image

    oversized = tmp_path / "huge.png"
    Image.new("RGB", (_MAX_LONG_EDGE_PX * 2, 100), color=(10, 20, 30)).save(oversized)

    llm = FakeVisionLLM()
    llm.provider = "anthropic"
    tool = VisionReviewTool(llm=llm, workspace_dir=str(tmp_path), allow_full_access=True)

    result = await tool.execute(image_paths=["huge.png"])

    assert result.success, result.error
    blocks = llm.messages[1].content
    image_block = next(block for block in blocks if block.get("type") == "image")
    sent_bytes = base64.b64decode(image_block["source"]["data"])
    with Image.open(io.BytesIO(sent_bytes)) as sent:
        assert max(sent.size) == _MAX_LONG_EDGE_PX
        assert sent.size == (_MAX_LONG_EDGE_PX, 50)


@pytest.mark.asyncio
async def test_vision_review_keeps_small_image_bytes_unchanged(tmp_path: Path):
    """Images within the ceiling are sent byte-for-byte (no re-encode)."""
    image = tmp_path / "slide.png"
    image.write_bytes(_ONE_PIXEL_PNG)
    llm = FakeVisionLLM()
    llm.provider = "anthropic"
    tool = VisionReviewTool(llm=llm, workspace_dir=str(tmp_path), allow_full_access=True)

    result = await tool.execute(image_paths=["slide.png"])

    assert result.success, result.error
    blocks = llm.messages[1].content
    image_block = next(block for block in blocks if block.get("type") == "image")
    assert base64.b64decode(image_block["source"]["data"]) == _ONE_PIXEL_PNG


@pytest.mark.asyncio
async def test_vision_review_times_out(tmp_path: Path, monkeypatch):
    """A slow LLM call is bounded by the vision review timeout."""
    import box_agent.tools.vision_review_tool as module

    monkeypatch.setattr(module, "_VISION_REVIEW_TIMEOUT", 0.05)

    class SlowLLM:
        provider = "openai"

        async def generate(self, messages, tools=None, *, thinking_enabled=False, call_kind=""):
            await asyncio.sleep(1.0)
            return LLMResponse(content="never", finish_reason="stop")

    image = tmp_path / "slide.png"
    image.write_bytes(_ONE_PIXEL_PNG)
    tool = VisionReviewTool(llm=SlowLLM(), workspace_dir=str(tmp_path), allow_full_access=True)

    result = await tool.execute(image_paths=["slide.png"])

    assert not result.success
    assert "timed out" in result.error
    assert not (tmp_path / "visual_review.md").exists()


class ToolConfig:
    class Tools:
        enable_bash = False
        enable_file_tools = False
        enable_todo = False
        enable_sub_agent = False

    tools = Tools()


def test_add_workspace_tools_registers_vision_review_when_llm_is_available(tmp_path: Path):
    tools = []

    add_workspace_tools(
        tools,
        ToolConfig(),
        tmp_path,
        allow_full_access=False,
        llm=FakeVisionLLM(),
        output=lambda *_: None,
    )

    assert any(tool.name == "vision_review" for tool in tools)


def test_add_workspace_tools_omits_vision_review_for_known_text_only_model(tmp_path: Path):
    class TextOnlyLLM:
        model = "deepseek-v4-pro"
        api_base = "https://api.deepseek.com"

    tools = []

    add_workspace_tools(
        tools,
        ToolConfig(),
        tmp_path,
        allow_full_access=False,
        llm=TextOnlyLLM(),
        output=lambda *_: None,
    )

    assert not any(tool.name == "vision_review" for tool in tools)


def test_add_workspace_tools_routes_vision_review_to_catalog_vision_model(tmp_path: Path):
    class RoutedLLM:
        model = "text-model"
        api_base = "https://example.test/v1"
        auto_model_candidates = (
            {"model": "text-model", "tags": ["code"], "abilityLevel": 4},
            {
                "model": "vision-model",
                "tags": ["vision"],
                "abilityLevel": 5,
                "maxTokens": 8192,
            },
        )

        def for_model(self, model, *, max_output_tokens=None):
            selected = FakeVisionLLM()
            selected.model = model
            selected.max_output_tokens = max_output_tokens
            return selected

    tools = []

    add_workspace_tools(
        tools,
        ToolConfig(),
        tmp_path,
        allow_full_access=False,
        llm=RoutedLLM(),
        output=lambda *_: None,
    )

    vision_tool = next(tool for tool in tools if tool.name == "vision_review")
    assert vision_tool.llm.model == "vision-model"
    assert vision_tool.llm.max_output_tokens == 8192
