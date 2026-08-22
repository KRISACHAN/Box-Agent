import json

from box_agent.evidence import extract_search_result_evidence


def test_extract_search_result_evidence_binds_each_summary_to_its_url():
    first_url = "https://example.com/report-one?utm_source=search"
    second_url = "https://example.org/report-two"
    evidence = extract_search_result_evidence(
        json.dumps(
            {
                "refs": [
                    {
                        "url": first_url,
                        "title": "Report one",
                        "summary": "Alpha published the first result.",
                    },
                    {
                        "url": second_url,
                        "title": "Report two",
                        "snippet": "Beta published the second result.",
                    },
                ]
            }
        )
    )

    assert evidence == {
        "https://example.com/report-one": (
            "Report one\nAlpha published the first result."
        ),
        second_url: "Report two\nBeta published the second result.",
    }
    assert "Beta" not in evidence["https://example.com/report-one"]


def test_extract_search_result_evidence_ignores_unstructured_or_title_only_rows():
    assert extract_search_result_evidence("Result: https://example.com/report") == {}
    assert (
        extract_search_result_evidence(
            {"results": [{"url": "https://example.com/report", "title": "Report"}]}
        )
        == {}
    )


def test_extract_search_result_evidence_accepts_nested_single_result():
    assert extract_search_result_evidence(
        {
            "data": {
                "url": "https://example.com/report",
                "title": "Example report",
                "description": "Example summary text.",
            }
        }
    ) == {
        "https://example.com/report": "Example report\nExample summary text."
    }
