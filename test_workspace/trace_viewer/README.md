# Offline ACP Trace Viewer

FastAPI/Jinja2/HTMX viewer for `box-agent-acp-eval/v1` output. It is a read-only diagnostic tool intended for a trusted local network. It has no authentication or token.

## Start

From the Box-Agent repository root:

```bash
uv sync --project test_workspace/trace_viewer
uv run --project test_workspace/trace_viewer trace-viewer \
  --repo-root "$PWD" \
  --host 0.0.0.0 \
  --port 8000
```

Open `http://<machine-ip>:8000/` from the local machine or a trusted LAN peer.

The data root is always `<repo-root>/test_workspace/outputs/`. There is no alternate output-root setting, legacy-format adapter, authentication, mutation endpoint, or redaction layer.

## Pages

- Evaluation directory list
- Case list with search and stderr category counts
- Case overview and final answer
- Unified timeline
- Independent Agent, ACP, process/stderr, and file pages

Record pages start at the earliest event and paginate only between complete records.
