"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from trace_viewer.repository import EvaluationRepository, NotFoundError
from trace_viewer.timeline import page_records, source_records, unified_timeline


PROJECT_DIR = Path(__file__).resolve().parents[2]


def create_app(repo_root: Path) -> FastAPI:
    app = FastAPI(title="ACP 离线评测查看器", docs_url=None, redoc_url=None)
    repository = EvaluationRepository(repo_root)
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
        return templates.TemplateResponse(request, "case.html", {"run_name": run_name, "case": case, "active": "overview"})

    def render_records(request: Request, run_name: str, case_id: str, source: str, page: int):
        try:
            case = repository.get_case(run_name, case_id)
        except NotFoundError as error:
            raise HTTPException(404, "任务不存在") from error
        records = unified_timeline(case["attempt_path"]) if source == "timeline" else source_records(case["attempt_path"], source)
        shown, next_page = page_records(records, page)
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
