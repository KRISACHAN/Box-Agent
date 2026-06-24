import base64
import json
from pathlib import Path

import httpx
import pytest

from box_agent.config import ImageGenerationConfig, ToolsConfig
from box_agent.tools.image_generation_tool import GenerateImageTool
from box_agent.tools.setup import add_workspace_tools


PNG_BYTES = b"\x89PNG\r\n\x1a\nimage-bytes"
JPEG_BYTES = b"\xff\xd8\xff\xe0jpeg-bytes"


def patch_async_client(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **_: original(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_generate_image_requires_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOX_AGENT_IMAGE_GENERATION_ENDPOINT", raising=False)
    monkeypatch.delenv("BOX_AGENT_IMAGE_GEN_ENDPOINT", raising=False)

    tool = GenerateImageTool(workspace_dir=str(tmp_path), allow_full_access=False)
    result = await tool.execute(prompt="test", output_path="assets/generated/test.png")

    assert not result.success
    assert "BOX_AGENT_IMAGE_GENERATION_ENDPOINT" in (result.error or "")


@pytest.mark.asyncio
async def test_generate_image_saves_base64_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer secret"
        assert payload == {
            "model": "gpt-image-1",
            "prompt": "editorial hero\n\nStyle: magazine illustration\n\nAvoid: text",
            "size": "1536x1024",
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
                    }
                ]
            },
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
        api_key="secret",
    )

    result = await tool.execute(
        prompt="editorial hero",
        output_path="assets/generated/hero.png",
        width=1600,
        height=900,
        style="magazine illustration",
        negative_prompt="text",
        metadata={"slide": "03"},
    )

    assert result.success
    assert (tmp_path / "assets/generated/hero.png").read_bytes() == PNG_BYTES
    assert result.raw_output
    assert result.raw_output["type"] == "artifact"
    assert result.raw_output["kind"] == "image"
    assert result.raw_output["filename"] == "hero.png"
    assert result.raw_output["rel_path"] == "assets/generated/hero.png"
    assert result.raw_output["abs_path"] == str(tmp_path / "assets/generated/hero.png")
    assert result.raw_output["uri"] == (tmp_path / "assets/generated/hero.png").as_uri()
    assert result.raw_output["mime"] == "image/png"
    assert result.raw_output["size_bytes"] == len(PNG_BYTES)
    assert result.raw_output["path"] == "assets/generated/hero.png"
    assert result.raw_output["mime_type"] == "image/png"
    assert result.raw_output["width"] == 1536
    assert result.raw_output["height"] == 1024
    assert result.raw_output["size"] == "1536x1024"
    assert result.raw_output["requested_height"] == 900
    assert "assets/generated/hero.png" in result.content


@pytest.mark.asyncio
async def test_generate_image_saves_relative_paths_under_output_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(PNG_BYTES).decode("ascii")}]},
        )

    patch_async_client(monkeypatch, handler)
    artifact_root = tmp_path / "session-a" / "output"
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        output_dir=str(artifact_root),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
        api_key="secret",
    )

    result = await tool.execute(prompt="hero", output_path="assets/generated/hero.png")

    target = artifact_root / "assets/generated/hero.png"
    assert result.success
    assert target.read_bytes() == PNG_BYTES
    assert not (tmp_path / "assets/generated/hero.png").exists()
    assert result.raw_output["rel_path"] == "session-a/output/assets/generated/hero.png"
    assert result.raw_output["abs_path"] == str(target)


@pytest.mark.asyncio
async def test_generate_image_accepts_explicit_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["size"] == "2048x2048"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
                    }
                ]
            },
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
    )

    result = await tool.execute(
        prompt="seasonal sequence",
        output_path="assets/generated/seasonal.png",
        size="2048x2048",
    )

    assert result.success
    assert (tmp_path / "assets/generated/seasonal.png").read_bytes() == PNG_BYTES
    assert result.raw_output
    assert result.raw_output["path"] == "assets/generated/seasonal.png"
    assert result.raw_output["size"] == "2048x2048"
    assert result.raw_output["width"] == 2048
    assert result.raw_output["height"] == 2048


@pytest.mark.asyncio
async def test_generate_image_upscales_too_small_explicit_size_for_openai_style_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["size"] == "1366x768"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
                    }
                ]
            },
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
    )

    result = await tool.execute(
        prompt="wide edit frame",
        output_path="assets/generated/wide-safe.png",
        size="1024x576",
    )

    assert result.success
    assert result.raw_output
    assert result.raw_output["size"] == "1366x768"
    assert result.raw_output["width"] == 1366
    assert result.raw_output["height"] == 768


@pytest.mark.asyncio
async def test_generate_image_saves_direct_image_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
    )

    result = await tool.execute(prompt="direct image", output_path="assets/generated/direct")

    assert result.success
    assert (tmp_path / "assets/generated/direct.png").read_bytes() == PNG_BYTES
    assert result.raw_output
    assert result.raw_output["path"] == "assets/generated/direct.png"


@pytest.mark.asyncio
async def test_generate_image_downloads_url_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://image.example.test/v1/images/generations":
            return httpx.Response(200, json={"url": "https://cdn.example.test/image.webp"})
        return httpx.Response(200, content=b"webp", headers={"content-type": "image/webp"})

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
    )

    result = await tool.execute(prompt="url image", output_path="assets/generated/from-url")

    assert result.success
    assert (tmp_path / "assets/generated/from-url.webp").read_bytes() == b"webp"
    assert result.raw_output
    assert result.raw_output["mime_type"] == "image/webp"


@pytest.mark.asyncio
async def test_generate_image_accepts_minimax_image_base64_list_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "image_base64": [
                        base64.b64encode(JPEG_BYTES).decode("ascii"),
                    ],
                },
            },
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://api.minimaxi.com/v1/image_generation",
    )

    result = await tool.execute(prompt="minimax image", output_path="assets/generated/minimax")

    assert result.success
    assert (tmp_path / "assets/generated/minimax.jpg").read_bytes() == JPEG_BYTES
    assert result.raw_output
    assert result.raw_output["path"] == "assets/generated/minimax.jpg"
    assert result.raw_output["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_generate_image_accepts_nested_image_url_list_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://image.example.test/v1/images/generations":
            return httpx.Response(
                200,
                json={"result": {"image_urls": ["https://cdn.example.test/nested.webp"]}},
            )
        return httpx.Response(200, content=b"webp", headers={"content-type": "image/webp"})

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
    )

    result = await tool.execute(prompt="nested url", output_path="assets/generated/nested")

    assert result.success
    assert (tmp_path / "assets/generated/nested.webp").read_bytes() == b"webp"


@pytest.mark.asyncio
async def test_generate_image_uses_auth_file_for_hosted_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"access_token": "login-token"}', encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer login-token"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-image-1"
        assert payload["size"] == "1536x1024"
        assert "wide image" in payload["prompt"]
        return httpx.Response(
            200,
            json={"b64_json": base64.b64encode(PNG_BYTES).decode("ascii")},
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.xiaohuanxiong.com/v1/images/generations",
        auth_file=str(auth_file),
    )

    result = await tool.execute(prompt="wide image", output_path="assets/generated/wide.png", width=4096, height=900)

    assert result.success
    assert result.raw_output
    assert result.raw_output["width"] == 1536
    assert result.raw_output["height"] == 1024
    assert result.raw_output["size"] == "1536x1024"


@pytest.mark.asyncio
async def test_generate_image_uses_default_size_for_seedream_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["size"] == "2048x2048"
        return httpx.Response(
            200,
            json={
                "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
            },
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://code-dev.xiaohuanxiong.com/api/web/llm/v2/images/gen",
        model="Doubao-Seedream-5.0-lite",
    )

    result = await tool.execute(
        prompt="seasonal courtyard",
        output_path="assets/generated/ds.png",
        width=1024,
        height=1024,
    )

    assert result.success
    assert (tmp_path / "assets/generated/ds.png").read_bytes() == PNG_BYTES
    assert result.raw_output
    assert result.raw_output["size"] == "2048x2048"


@pytest.mark.asyncio
async def test_generate_image_passes_explicit_size_through_for_remote_passthrough_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["size"] == "1024x1024"
        return httpx.Response(
            200,
            json={"b64_json": base64.b64encode(PNG_BYTES).decode("ascii")},
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="http://10.158.136.99:9000/api/web/llm/v2/images/gen",
    )

    result = await tool.execute(
        prompt="海边的落日",
        output_path="assets/generated/sunset.png",
        size="1024x1024",
    )

    assert result.success, result.error
    assert result.raw_output
    assert result.raw_output["size"] == "1024x1024"
    assert result.raw_output["image_mode"] == "text_to_image"


@pytest.mark.asyncio
async def test_generate_image_maps_seedream_explicit_size_to_supported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["size"] == "2848x1600"
        return httpx.Response(
            200,
            json={
                "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
            },
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://code-dev.xiaohuanxiong.com/api/web/llm/v2/images/gen",
        model="Doubao-Seedream-5.0-lite",
    )

    result = await tool.execute(
        prompt="unsupported ratio",
        output_path="assets/generated/ds-unsupported.png",
        size="2048x1024",
    )

    assert result.success
    assert result.raw_output
    assert result.raw_output["size"] == "2848x1600"


@pytest.mark.asyncio
async def test_generate_image_respects_seedream_exact_ratio_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["size"] == "4096x2304"
        return httpx.Response(
            200,
            json={
                "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
            },
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://code-dev.xiaohuanxiong.com/api/web/llm/v2/images/gen",
        model="Doubao-Seedream-5.0-lite",
    )

    result = await tool.execute(
        prompt="wide season",
        output_path="assets/generated/ds-wide.png",
        width=4096,
        height=2304,
    )

    assert result.success
    assert (tmp_path / "assets/generated/ds-wide.png").read_bytes() == PNG_BYTES
    assert result.raw_output
    assert result.raw_output["size"] == "4096x2304"


@pytest.mark.asyncio
async def test_generate_image_edits_reference_image_with_multipart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(PNG_BYTES)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://image.example.test/api/web/llm/v2/images/edits"
        assert request.headers["authorization"] == "Bearer secret"
        assert request.headers["content-type"].startswith("multipart/form-data")
        body = request.read()
        assert b'name="image"; filename="reference.png"' in body
        assert PNG_BYTES in body
        assert b'name="prompt"' in body
        assert "图片里添加水印".encode("utf-8") in body
        assert b'name="size"' in body
        assert b"1024x1024" in body
        assert b"gpt-image-1" not in body
        return httpx.Response(
            200,
            json={"b64_json": base64.b64encode(JPEG_BYTES).decode("ascii")},
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/api/web/llm/v2/images/gen",
        api_key="secret",
    )

    result = await tool.execute(
        prompt="图片里添加水印: 网宿科技",
        output_path="assets/generated/edited.jpg",
        size="1024x1024",
        image_mode="image_to_image",
        reference_images=["reference.png"],
    )

    assert result.success, result.error
    assert (tmp_path / "assets/generated/edited.jpg").read_bytes() == JPEG_BYTES
    assert result.raw_output
    assert result.raw_output["image_mode"] == "image_to_image"
    assert result.raw_output["reference_images"] == ["reference.png"]


@pytest.mark.asyncio
async def test_generate_image_edit_upscales_too_small_explicit_size_for_openai_style_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(PNG_BYTES)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'name="size"' in body
        assert b"1366x768" in body
        return httpx.Response(
            200,
            json={"b64_json": base64.b64encode(JPEG_BYTES).decode("ascii")},
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/api/web/llm/v2/images/gen",
    )

    result = await tool.execute(
        prompt="给图右下角加一个角标",
        output_path="assets/generated/edit-safe.jpg",
        size="1024x576",
        image_mode="image_to_image",
        reference_images=["reference.png"],
    )

    assert result.success, result.error
    assert result.raw_output
    assert result.raw_output["size"] == "1366x768"
    assert result.raw_output["width"] == 1366
    assert result.raw_output["height"] == 768


@pytest.mark.asyncio
async def test_generate_image_edit_requires_reference_image(tmp_path: Path) -> None:
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/api/web/llm/v2/images/gen",
    )

    result = await tool.execute(
        prompt="edit image",
        output_path="assets/generated/edit.png",
        image_mode="image_to_image",
    )

    assert not result.success
    assert "requires at least one reference image" in (result.error or "")


@pytest.mark.asyncio
async def test_generate_image_edit_rejects_reference_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-reference.png"
    outside.write_bytes(PNG_BYTES)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/api/web/llm/v2/images/gen",
    )

    result = await tool.execute(
        prompt="edit image",
        output_path="assets/generated/edit.png",
        reference_images=[str(outside)],
    )

    assert not result.success
    assert "outside the workspace" in (result.error or "")


@pytest.mark.asyncio
async def test_generate_image_rejects_output_outside_workspace(tmp_path: Path) -> None:
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
    )

    result = await tool.execute(prompt="bad path", output_path="../outside.png")

    assert not result.success
    assert "outside the workspace" in (result.error or "")


def test_add_workspace_tools_registers_generate_image(tmp_path: Path) -> None:
    tools = []

    class Config:
        tools = ToolsConfig(enable_bash=False, enable_file_tools=False, enable_todo=False, enable_sub_agent=False)

    add_workspace_tools(tools, Config(), tmp_path, allow_full_access=False, output=lambda *_: None)

    assert any(tool.name == "generate_image" for tool in tools)


def test_add_workspace_tools_passes_image_generation_config(tmp_path: Path) -> None:
    tools = []

    class LLM:
        auth_file = str(tmp_path / "auth.json")

    class Config:
        llm = LLM()
        tools = ToolsConfig(enable_bash=False, enable_file_tools=False, enable_todo=False, enable_sub_agent=False)
        image_generation = ImageGenerationConfig(
            endpoint="https://image.example.test/v1/images/generations",
            api_key="image-token",
            model="chatgpt-image-latest",
            timeout=45.0,
        )

    add_workspace_tools(tools, Config(), tmp_path, allow_full_access=False, output=lambda *_: None)

    tool = next(tool for tool in tools if tool.name == "generate_image")
    assert isinstance(tool, GenerateImageTool)
    assert tool.endpoint == "https://image.example.test/v1/images/generations"
    assert tool.api_key == "image-token"
    assert tool.model == "chatgpt-image-latest"
    assert tool.auth_file == str(tmp_path / "auth.json")
    assert tool.timeout == 45.0


def _real_png(size=(256, 256), color=(40, 40, 40)) -> bytes:
    import io as _io

    from PIL import Image as _Image

    buf = _io.BytesIO()
    _Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _b64_handler(payload_bytes: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(payload_bytes).decode("ascii")}]},
        )

    return handler


@pytest.mark.asyncio
async def test_generate_image_watermarks_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _real_png()
    patch_async_client(monkeypatch, _b64_handler(source))
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
        api_key="secret",
    )

    result = await tool.execute(prompt="hero", output_path="assets/generated/hero.png")

    assert result.success, result.error
    saved = (tmp_path / "assets/generated/hero.png").read_bytes()
    assert saved != source  # watermark changed the bytes
    assert result.raw_output["watermark"]["applied"] is True
    assert "watermark: applied" in result.content


@pytest.mark.asyncio
async def test_generate_image_watermark_disabled_keeps_original_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _real_png()
    patch_async_client(monkeypatch, _b64_handler(source))
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
        api_key="secret",
    )

    result = await tool.execute(
        prompt="hero",
        output_path="assets/generated/plain.png",
        watermark=False,
    )

    assert result.success, result.error
    saved = (tmp_path / "assets/generated/plain.png").read_bytes()
    assert saved == source  # untouched
    assert result.raw_output["watermark"]["applied"] is False
    assert result.raw_output["watermark"]["reason"] == "disabled by caller"


@pytest.mark.asyncio
async def test_generate_image_custom_watermark_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _real_png()
    patch_async_client(monkeypatch, _b64_handler(source))
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
        api_key="secret",
    )

    result = await tool.execute(
        prompt="hero",
        output_path="assets/generated/branded.png",
        watermark_text="网宿科技",
    )

    assert result.success, result.error
    saved = (tmp_path / "assets/generated/branded.png").read_bytes()
    assert saved != source
    assert result.raw_output["watermark"]["applied"] is True


@pytest.mark.asyncio
async def test_generate_image_edit_path_is_also_watermarked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _real_png()
    (tmp_path / "reference.png").write_bytes(_real_png(color=(10, 10, 10)))
    patch_async_client(monkeypatch, _b64_handler(source))
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/api/web/llm/v2/images/gen",
        api_key="secret",
    )

    result = await tool.execute(
        prompt="restyle",
        output_path="assets/generated/edited.png",
        image_mode="image_to_image",
        reference_images=["reference.png"],
    )

    assert result.success, result.error
    saved = (tmp_path / "assets/generated/edited.png").read_bytes()
    assert saved != source
    assert result.raw_output["image_mode"] == "image_to_image"
    assert result.raw_output["watermark"]["applied"] is True


@pytest.mark.asyncio
async def test_generate_image_svg_response_skips_watermark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svg_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'><rect/></svg>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=svg_bytes,
            headers={"content-type": "image/svg+xml"},
        )

    patch_async_client(monkeypatch, handler)
    tool = GenerateImageTool(
        workspace_dir=str(tmp_path),
        allow_full_access=False,
        endpoint="https://image.example.test/v1/images/generations",
        api_key="secret",
    )

    result = await tool.execute(prompt="logo", output_path="assets/generated/logo.svg")

    assert result.success, result.error
    saved = (tmp_path / "assets/generated/logo.svg").read_bytes()
    assert saved == svg_bytes  # vector untouched
    assert result.raw_output["watermark"]["applied"] is False
