# 离线 ACP 评测与 Trace Viewer

`test_workspace/` 用于通过 ACP 运行离线评测，并在本地或可信局域网中查看完整执行过程。

## 评测集

仓库自带 3 条纯文本、无附件的 smoke-test：

```text
test_workspace/inputs/smoke_test/dataset.jsonl
```

评测集使用 JSONL 格式，每个非空行是一个 Case，至少包含：

- `id`：Case 的唯一标识。
- `query`：发送给 Agent 的任务。
- `input_files`：输入文件路径列表；路径相对于评测集所在目录。

## 运行评测

从仓库根目录准备依赖：

```bash
uv sync
uv sync --project test_workspace/acp_eval
```

运行默认 smoke-test：

```bash
uv run python test_workspace/run_acp_eval.py --count 3 --title smoke-test
```

运行本地完整评测集：

```bash
uv run python test_workspace/run_acp_eval.py \
  --dataset test_workspace/inputs/hermes_antilia_v2/dataset.jsonl \
  --count 69 \
  --title first
```

运行指定 Case：

```bash
uv run python test_workspace/run_acp_eval.py \
  --case-id Q36 \
  --case-id Q58 \
  --title selected
```

评测只使用 ACP 入口。结果写入 `test_workspace/outputs/yymmdd-hhmm-<title>/`。
完整评测集及其输入文件只保存在本地，不提交到 Git。

更多参数可运行：

```bash
uv run python test_workspace/run_acp_eval.py --help
```

## 启动 Trace Viewer

安装 Viewer 依赖：

```bash
uv sync --project test_workspace/trace_viewer
```

启动服务：

```bash
uv run --project test_workspace/trace_viewer trace-viewer \
  --repo-root "$PWD" \
  --host 0.0.0.0 \
  --port 8000
```

本机访问 `http://127.0.0.1:8000/`，局域网同事使用 `http://<本机 IP>:8000/`。
Viewer 为只读工具，不包含认证或脱敏能力，只应在可信网络中使用。

详细规范见 [AGENTS.md](AGENTS.md)，组件说明见 [acp_eval/README.md](acp_eval/README.md) 和 [trace_viewer/README.md](trace_viewer/README.md)。
