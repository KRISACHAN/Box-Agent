"""A managed MCP subprocess reads the endpoint policy from its own profile."""

import json
import sys
from pathlib import Path

import pytest

from box_agent.tools.mcp_bootstrap import bootstrap_managed_mcp_config
from box_agent.tools.mcp_loader import MCPServerConnection


@pytest.mark.asyncio
async def test_managed_web_mcp_reads_disabled_policy_and_sends_compatible_wire(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    (root / "config").mkdir(parents=True)
    monkeypatch.setenv("BOX_AGENT_HOME", str(root))
    (root / "config/config.yaml").write_text(
        "api_key: test\napi_base: https://inference.example/v1\nprovider: openai\n"
        "model: SenseNova-Flash-test\nreasoning_effort_when_disabled: low\n")
    child = tmp_path / "web_extract_mock.py"
    child.write_text('''
import json, os, sys
sys.path.insert(0, sys.argv[1])
assert os.environ.get("BOX_AGENT_HOME") == sys.argv[2]
import httpx
from openai import AsyncOpenAI
from box_agent.mcp_servers import web_extract_server as server
from box_agent.mcp_servers.web_extract import WebExtractTool, _FetchedPage

original = server._create_configured_llm
def configured():
    llm = original()
    original_client = llm._client.client
    async def transport(request):
        await original_client.close()
        body = json.loads(request.content)
        if body.get("reasoning_effort") != "low":
            return httpx.Response(422, json={"error": {"message": "Only low/medium/high accepted"}})
        return httpx.Response(200, json={"id": "mock", "created": 1, "model": llm.model,
            "object": "chat.completion", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": "wire reasoning_effort=low"}}]})
    llm._client.client = AsyncOpenAI(api_key="test", base_url=llm.api_base,
        max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    return llm
async def fake_fetch(self, url):
    return _FetchedPage(content="Source evidence. " * 3000, final_url=url)
server._create_configured_llm = configured
WebExtractTool._fetch = fake_fetch
server.main()
''')
    config = root / "config/mcp.json"
    bootstrap_managed_mcp_config(config, web_extract_command=sys.executable)
    entry = json.loads(config.read_text())["mcpServers"]["box-agent-web-extract"]
    connection = MCPServerConnection(name="box-agent-web-extract", command=sys.executable,
        args=[str(child), str(Path(__file__).resolve().parents[1]), str(root.resolve())],
        env=entry["env"], connect_timeout=15, execute_timeout=15)
    try:
        assert await connection.connect()
        result = await connection.session.call_tool("web_extract", {"url": "https://example.invalid/article"})
        assert not result.isError, result.content
        assert "wire reasoning_effort=low" in result.content[0].text
    finally:
        await connection.disconnect()
