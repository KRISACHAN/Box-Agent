"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import Markup

from trace_viewer.presentation import annotate_timing, json_text, present_record
from trace_viewer.repository import EvaluationRepository, NotFoundError
from trace_viewer.timeline import page_records, source_records, unified_timeline


PROJECT_DIR = Path(__file__).resolve().parents[2]


def create_app(repo_root: Path) -> FastAPI:
    app = FastAPI(title="ACP 离线评测查看器", docs_url=None, redoc_url=None)
    repository = EvaluationRepository(repo_root)
    markdown = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    templates = Jinja2Templates(directory=PROJECT_DIR / "templates")
    app.mount("/static", StaticFiles(directory=PROJECT_DIR / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(request, "index.html", {"runs": repository.list_runs()})

    @app.get("/runs/{run_name}", response_class=HTMLResponse)
    def run_page(request: Request, run_name: str, q: str = ""):
        try:
            cases = repository.list_cases(run_name, q)
        except NotFoundError as error:
            raise HTTPException(404, "评测目录不存在") from error
        return templates.TemplateResponse(request, "run.html", {"run_name": run_name, "cases": cases, "query": q})

    @app.get("/runs/{run_name}/cases/{case_id}", response_class=HTMLResponse)
    def case_overview(request: Request, run_name: str, case_id: str):
        try:
            case = repository.get_case(run_name, case_id)
        except NotFoundError as error:
            raise HTTPException(404, "任务不存在") from error
        return templates.TemplateResponse(
            request,
            "case.html",
            {
                "run_name": run_name,
                "case": case,
                "input_text": json_text(case["input"]),
                "active": "overview",
            },
        )

    def render_records(request: Request, run_name: str, case_id: str, source: str, page: int):
        try:
            case = repository.get_case(run_name, case_id)
        except NotFoundError as error:
            raise HTTPException(404, "任务不存在") from error
        records = unified_timeline(case["attempt_path"]) if source == "timeline" else source_records(case["attempt_path"], source)
        records = annotate_timing(records)
        shown, next_page = page_records(records, page)
        shown = [present_record(record) for record in shown]
        context = {"run_name": run_name, "case": case, "active": source, "source": source, "records": shown, "next_page": next_page}
        if request.headers.get("HX-Request") == "true":
            return templates.TemplateResponse(request, "_records.html", context)
        return templates.TemplateResponse(request, "source.html", context)

    @app.get("/runs/{run_name}/cases/{case_id}/timeline", response_class=HTMLResponse)
    def timeline_page(request: Request, run_name: str, case_id: str, page: int = 1):
        return render_records(request, run_name, case_id, "timeline", page)

    @app.get("/runs/{run_name}/cases/{case_id}/agent", response_class=HTMLResponse)
    def agent_page(request: Request, run_name: str, case_id: str, page: int = 1):
        return render_records(request, run_name, case_id, "agent", page)

    @app.get("/runs/{run_name}/cases/{case_id}/acp", response_class=HTMLResponse)
    def acp_page(request: Request, run_name: str, case_id: str, page: int = 1):
        return render_records(request, run_name, case_id, "acp", page)

    @app.get("/runs/{run_name}/cases/{case_id}/process", response_class=HTMLResponse)
    def process_page(request: Request, run_name: str, case_id: str, page: int = 1):
        return render_records(request, run_name, case_id, "process", page)

    @app.get("/runs/{run_name}/cases/{case_id}/diagnosis", response_class=HTMLResponse)
    def diagnosis_page(request: Request, run_name: str, case_id: str):
        try:
            case = repository.get_case(run_name, case_id)
            content = repository.diagnosis_text(run_name, case_id)
        except NotFoundError as error:
            raise HTTPException(404, "任务不存在") from error
        rendered = Markup(markdown.render(content)) if content is not None else None
        return templates.TemplateResponse(
            request,
            "diagnosis.html",
            {
                "run_name": run_name,
                "case": case,
                "active": "diagnosis",
                "diagnosis": rendered,
            },
        )

    @app.get("/runs/{run_name}/cases/{case_id}/diagnosis/raw", response_class=PlainTextResponse)
    def diagnosis_raw(run_name: str, case_id: str):
        try:
            content = repository.diagnosis_text(run_name, case_id)
        except NotFoundError as error:
            raise HTTPException(404, "任务不存在") from error
        if content is None:
            raise HTTPException(404, "尚未生成诊断")
        return PlainTextResponse(content)

    @app.get("/runs/{run_name}/cases/{case_id}/diagnosis/download")
    def diagnosis_download(run_name: str, case_id: str):
        try:
            path = repository.diagnosis_path(run_name, case_id)
        except NotFoundError as error:
            raise HTTPException(404, "任务不存在") from error
        if path is None:
            raise HTTPException(404, "尚未生成诊断")
        return FileResponse(path, filename="diagnosis.md")

    @app.get("/runs/{run_name}/cases/{case_id}/files", response_class=HTMLResponse)
    def files_page(request: Request, run_name: str, case_id: str):
        try:
            case = repository.get_case(run_name, case_id)
        except NotFoundError as error:
            raise HTTPException(404, "任务不存在") from error
        files = [path.relative_to(case["attempt_path"]).as_posix() for path in sorted(case["attempt_path"].rglob("*")) if path.is_file()]
        return templates.TemplateResponse(request, "files.html", {"run_name": run_name, "case": case, "active": "files", "files": files})

    @app.get("/runs/{run_name}/cases/{case_id}/download/{relative_path:path}")
    def download(run_name: str, case_id: str, relative_path: str):
        try:
            path = repository.resolve_case_path(run_name, case_id, relative_path)
        except NotFoundError as error:
            raise HTTPException(404, "文件不存在") from error
        return FileResponse(path, filename=path.name)

    return app
