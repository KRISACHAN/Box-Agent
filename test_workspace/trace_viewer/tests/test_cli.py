from trace_viewer.cli import main


def test_cli_defaults_to_lan_binding(monkeypatch, repo_root):
    calls = []
    monkeypatch.setattr("trace_viewer.cli.uvicorn.run", lambda app, **kwargs: calls.append((app, kwargs)))
    assert main(["--repo-root", str(repo_root)]) == 0
    assert calls[0][1] == {"host": "0.0.0.0", "port": 8000}


def test_cli_allows_host_and_port_override(monkeypatch, repo_root):
    calls = []
    monkeypatch.setattr("trace_viewer.cli.uvicorn.run", lambda app, **kwargs: calls.append(kwargs))
    assert main(["--repo-root", str(repo_root), "--host", "127.0.0.1", "--port", "8899"]) == 0
    assert calls == [{"host": "127.0.0.1", "port": 8899}]
