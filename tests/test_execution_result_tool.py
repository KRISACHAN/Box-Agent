"""Tests for the host-neutral execution result contract."""

import pytest

from box_agent.tools.execution_result_tool import ReportExecutionResultTool


@pytest.fixture
def tool():
    return ReportExecutionResultTool()


@pytest.mark.asyncio
async def test_reports_completed_execution_result(tool):
    result = await tool.execute(
        outcome="completed",
        summary="Implemented the requested API and verified it.",
        changes=[
            {
                "kind": "code",
                "summary": "Added the project member directory endpoint.",
                "reference": "src/routes/projects.ts",
            }
        ],
        checks=[
            {
                "name": "integration tests",
                "status": "passed",
                "summary": "Client-readiness scenarios passed.",
                "reference": "tests/integration/client-readiness.test.ts",
            }
        ],
        known_limitations=["Production identity mapping remains host-owned."],
        questions=[],
    )

    assert result.success
    assert result.raw_output == {
        "type": "execution_result",
        "version": 1,
        "outcome": "completed",
        "summary": "Implemented the requested API and verified it.",
        "changes": [
            {
                "kind": "code",
                "summary": "Added the project member directory endpoint.",
                "reference": "src/routes/projects.ts",
            }
        ],
        "checks": [
            {
                "name": "integration tests",
                "status": "passed",
                "summary": "Client-readiness scenarios passed.",
                "reference": "tests/integration/client-readiness.test.ts",
            }
        ],
        "knownLimitations": ["Production identity mapping remains host-owned."],
        "questions": [],
    }


@pytest.mark.asyncio
async def test_completed_result_requires_a_real_change(tool):
    result = await tool.execute(
        outcome="completed",
        summary="Nothing changed.",
        changes=[],
        checks=[],
        known_limitations=[],
        questions=[],
    )

    assert not result.success
    assert result.error == "Completed execution results require at least one change."


@pytest.mark.asyncio
async def test_needs_input_result_requires_a_question(tool):
    result = await tool.execute(
        outcome="needs_input",
        summary="A product decision is required.",
        changes=[],
        checks=[],
        known_limitations=[],
        questions=[],
    )

    assert not result.success
    assert result.error == "needs_input execution results require at least one question."


def test_schema_is_host_neutral(tool):
    schema = tool.to_openai_schema()["function"]

    assert schema["name"] == "report_execution_result"
    assert "organization" not in str(schema).lower()
    assert "jwt" not in str(schema).lower()
    assert "service url" not in str(schema).lower()
    assert schema["parameters"]["additionalProperties"] is False
