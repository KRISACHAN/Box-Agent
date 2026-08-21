def test_three_level_navigation(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "eval-one" in home.text
    assert "2 个任务" in home.text

    run = client.get("/runs/eval-one")
    assert run.status_code == 200
    assert "Q1" in run.text and "Q2" in run.text
    assert run.text.count("type=\"search\"") == 1

    case = client.get("/runs/eval-one/cases/Q1")
    assert case.status_code == 200
    assert "Agent 轨迹" in case.text
    assert "最终回答" in case.text
    assert "answer Q1" in case.text


def test_case_overview_shows_complete_input_as_unicode(client, repo_root):
    input_path = repo_root / "test_workspace/outputs/eval-one/cases/Q1/input.json"
    input_path.write_text(
        '{"id":"Q1","query":"给我生成报告","input_files":["数据.csv"]}',
        encoding="utf-8",
    )

    response = client.get("/runs/eval-one/cases/Q1")

    assert response.status_code == 200
    assert "任务输入" in response.text
    assert "给我生成报告" in response.text
    assert "数据.csv" in response.text
    assert r"\u7ed9\u6211\u751f\u6210" not in response.text


def test_case_search(client):
    response = client.get("/runs/eval-one?q=Q2")
    assert response.status_code == 200
    assert "Q2" in response.text
    assert "Q1" not in response.text


def test_incomplete_case_remains_visible(client):
    response = client.get("/runs/eval-one")
    assert "incomplete" in response.text
    assert "error" in response.text


def test_unknown_run_and_case_return_404(client):
    assert client.get("/runs/missing").status_code == 404
    assert client.get("/runs/eval-one/cases/missing").status_code == 404


def test_all_case_evidence_pages(client):
    base = "/runs/eval-one/cases/Q1"
    expected = {
        "timeline": "统一时间线",
        "agent": "turn.start",
        "acp": "initialize",
        "process": "process.started",
        "files": "files-before.json",
    }
    for suffix, text in expected.items():
        response = client.get(f"{base}/{suffix}")
        assert response.status_code == 200
        assert text in response.text


def test_diagnosis_page_has_an_empty_state_without_a_markdown_file(client):
    response = client.get("/runs/eval-one/cases/Q1/diagnosis")

    assert response.status_code == 200
    assert "诊断结果" in response.text
    assert "尚未生成诊断" in response.text
    assert 'class="active" href="/runs/eval-one/cases/Q1/diagnosis"' in response.text


def test_diagnosis_page_renders_arbitrary_case_level_markdown(client, repo_root):
    case = repo_root / "test_workspace/outputs/eval-one/cases/Q1"
    (case / "diagnosis.md").write_text(
        "# 自由标题\n\n- 中文结论\n\n`stderr`\n\n| 项目 | 结论 |\n| --- | --- |\n| 轨迹 | 正常 |\n\n<aside data-note=\"kept\">任意 HTML</aside>\n",
        encoding="utf-8",
    )

    response = client.get("/runs/eval-one/cases/Q1/diagnosis")

    assert response.status_code == 200
    assert "<h1>自由标题</h1>" in response.text
    assert "<li>中文结论</li>" in response.text
    assert "<code>stderr</code>" in response.text
    assert "<table>" in response.text
    assert "<td>正常</td>" in response.text
    assert '<aside data-note="kept">任意 HTML</aside>' in response.text
    assert "查看原始 Markdown" in response.text
    assert "下载 Markdown" in response.text


def test_diagnosis_raw_and_download_return_the_unmodified_case_file(client, repo_root):
    case = repo_root / "test_workspace/outputs/eval-one/cases/Q1"
    content = "# 任意内容\n\n\\u7ed9 and 中文\n"
    (case / "diagnosis.md").write_text(content, encoding="utf-8")

    raw = client.get("/runs/eval-one/cases/Q1/diagnosis/raw")
    download = client.get("/runs/eval-one/cases/Q1/diagnosis/download")

    assert raw.status_code == 200
    assert raw.text == content
    assert raw.headers["content-type"].startswith("text/plain")
    assert download.status_code == 200
    assert download.content == content.encode()
    assert "attachment" in download.headers["content-disposition"]


def test_missing_diagnosis_raw_and_download_return_404(client):
    base = "/runs/eval-one/cases/Q1/diagnosis"

    assert client.get(f"{base}/raw").status_code == 404
    assert client.get(f"{base}/download").status_code == 404


def test_record_pages_show_elapsed_times_unicode_summary_and_collapsible_raw_data(client, repo_root):
    trace = repo_root / "test_workspace/outputs/eval-one/cases/Q1/attempts/attempt-q1/agent/trace.jsonl"
    trace.write_text(
        "\n".join(
            [
                '{"event":"turn.input","timestamp":"2026-08-21T09:59:59+00:00","data":{"content":"给我生成页面"}}',
                '{"event":"tool.request","timestamp":"2026-08-21T10:00:00.250+00:00","session_id":"hidden-session","data":{"tool_name":"write_file","arguments":{"path":"页面.html","content":"完整原文"}}}',
                '{"event":"tool.response","timestamp":"2026-08-21T10:00:02.500+00:00","data":{"tool_name":"write_file","success":true,"content":"写入成功"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    response = client.get("/runs/eval-one/cases/Q1/agent")

    assert response.status_code == 200
    assert "工具调用" in response.text
    assert "write_file" in response.text
    assert "页面.html" in response.text
    assert "给我生成页面" in response.text
    assert r"\u7ed9\u6211\u751f\u6210" not in response.text
    assert "+0.000s" in response.text
    assert "+1.250s" in response.text
    assert "Δ1.250s" in response.text
    assert "+3.500s" in response.text
    assert "Δ2.250s" in response.text
    assert response.text.count('class="raw-data"') == 3
    assert "Raw Data" in response.text
    assert 'src="/static/chevron.svg"' in response.text


def test_each_timestamped_record_page_uses_the_same_elapsed_labels(client):
    base = "/runs/eval-one/cases/Q1"

    for source in ("timeline", "agent", "acp", "process"):
        response = client.get(f"{base}/{source}")
        assert response.status_code == 200
        assert "距开始" in response.text
        assert "+0.000s" in response.text


def test_process_and_timeline_have_start_elapsed_seconds_for_every_block(client):
    base = "/runs/eval-one/cases/Q1"

    for source in ("timeline", "process"):
        response = client.get(f"{base}/{source}")
        assert response.status_code == 200
        assert "距开始 <strong>—</strong>" not in response.text


def test_unified_timeline_elapsed_time_uses_full_order_before_paging(client):
    response = client.get("/runs/eval-one/cases/Q1/timeline")

    assert response.status_code == 200
    assert "+0.500s" in response.text
    assert "Δ0.500s" in response.text
    assert "+1.000s" in response.text


def test_htmx_record_page_returns_fragment(client):
    response = client.get(
        "/runs/eval-one/cases/Q1/timeline?page=1",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "<!doctype html>" not in response.text.lower()
    assert "record-card" in response.text


def test_load_more_replaces_its_previous_control(client, repo_root):
    protocol = repo_root / "test_workspace/outputs/eval-one/cases/Q1/attempts/attempt-q1/protocol.jsonl"
    protocol.write_text(
        "".join('{"sequence": %d, "message": {}}\n' % index for index in range(205)),
        encoding="utf-8",
    )
    response = client.get(
        "/runs/eval-one/cases/Q1/timeline?page=1",
        headers={"HX-Request": "true"},
    )
    assert "load-more" in response.text
    assert 'hx-target="this"' in response.text
    assert 'hx-swap="outerHTML"' in response.text


def test_download_is_contained_in_attempt(client, repo_root):
    attempt = repo_root / "test_workspace/outputs/eval-one/cases/Q1/attempts/attempt-q1"
    (attempt / "workspace").mkdir()
    (attempt / "workspace/demo.txt").write_text("hello", encoding="utf-8")
    response = client.get("/runs/eval-one/cases/Q1/download/workspace/demo.txt")
    assert response.status_code == 200
    assert response.text == "hello"
    assert client.get("/runs/eval-one/cases/Q1/download/../../../../etc/passwd").status_code in {404, 422}
