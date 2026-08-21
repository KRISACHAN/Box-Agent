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
