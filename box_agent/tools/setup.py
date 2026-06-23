"""Tool initialization helpers shared by CLI and ACP entry-points.

Extracted from ``cli.py`` so that ``box_agent.acp`` can assemble the
tool belt without pulling in ``prompt_toolkit`` and the rest of the
interactive-CLI surface.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from box_agent.config import Config
from box_agent.tools.base import Tool
from box_agent.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
from box_agent.tools.file_tools import EditTool, ReadTool, WriteTool
from box_agent.tools.image_generation_tool import GenerateImageTool
from box_agent.tools.jupyter_tool import (
    JupyterSandboxTool,
    MAX_EXECUTE_CODE_CHARS,
    SandboxEnvironment,
    SandboxStatusTool,
)
from box_agent.tools.mcp_loader import load_mcp_tools_async, set_mcp_timeout_config
from box_agent.tools.memory_tool import MemoryReadTool, MemorySearchTool, MemoryWriteTool
from box_agent.tools.obsidian_tool import create_obsidian_tools
from box_agent.tools.plan_tool import PlanReadTool, PlanStore, PlanWriteTool
from box_agent.tools.runtime import SkillRuntimeContext, build_skill_runtime_context
from box_agent.tools.schedule_tool import CreateScheduledTaskTool
from box_agent.tools.skill_tool import create_skill_tools
from box_agent.tools.sub_agent_tool import SubAgentTool
from box_agent.tools.todo_tool import TodoReadTool, TodoStore, TodoWriteTool
from box_agent.tools.vision_review_tool import VisionReviewTool

if TYPE_CHECKING:
    from box_agent.tools.permissions import PermissionEngine


def build_sandbox_info_prompt(use_output_dir: bool = True) -> str:
    """Build the sandbox prompt block for output or project workspace mode."""
    if use_output_dir:
        location_line = (
            "沙箱有独立 `sys.executable`，cwd 已是 `{workspace}/output/`"
            "（或 host 指定的当前会话 output 根），"
            "存盘用相对路径（如 `plt.savefig(\"chart.png\")`）；禁写 `/mnt/data/`、"
            "`sandbox:` 前缀；读用户上传文件用 `../<name>` 回 workspace 根。"
        )
    else:
        location_line = (
            "沙箱有独立 `sys.executable`，cwd 已是当前工作区/代码项目根目录，"
            "存盘用项目内相对路径；不要默认创建或使用 `output/` 目录；"
            "禁写 `/mnt/data/`、`sandbox:` 前缀。"
        )

    return f"""
## Python Sandbox (execute_code)

Python 代码通过 `execute_code` 在**隔离 Jupyter kernel** 中运行，和 host Python 独立：

- **运行位置**：{location_line}
- **状态持久**：同会话内变量、import、已加载数据保留到下一次调用；保持分步执行避免错误。
- **预装包**：pandas、numpy、matplotlib、seaborn、scikit-learn、openpyxl、xlrd、python-docx、pypdf、pdfplumber、reportlab、python-pptx、beautifulsoup4、lxml、pillow、requests、pyyaml、python-dateutil、chardet + 标准库——**不要重装**，会拖慢首次执行。
- **装新包**：仅在确认缺失时，在 `execute_code` 内用 `%pip install <pkg>` / `!pip install <pkg>`（走当前 kernel 的 pip，落沙箱 venv）。**绝对禁止** `bash` 跑 `pip install`——会装到 host，沙箱仍 `ModuleNotFoundError`。
- **用 execute_code**：数据分析、可视化、CSV/Excel/JSON/图片读写、Word/PDF/PPT 处理、多步计算、需保留状态的脚本。
- **单次代码大小**：每次 `execute_code(code=...)` 控制在 {MAX_EXECUTE_CODE_CHARS} 字符以内；大脚本/模板/数据/共享样式/HTML/CSS/JS/JSON manifest/base64/生成文件正文，要预先分段执行或落盘后分块追加，最后再读取校验；不要等到 `EXECUTE_CODE_TOO_LARGE` 后才拆，也不要把大段内容塞进一个工具参数。
- **必须执行**：用户要求“用/使用/运行 Python”得到一个具体结果（如生成随机数、计算数值、处理数据/文件、运行脚本）时，必须调用 `execute_code` 返回真实执行结果；不要只给代码示例。只有用户明确问“怎么写/示例代码/解释代码”时才只返回代码。
- **用 bash**：仓库代码编辑、测试/构建、系统命令、git——与沙箱无关。

### 文档处理优先级

Excel/Word/PDF/PowerPoint 优先在沙箱内用 Python 包，避免外部 CLI：

- **Excel**：`pandas`+`openpyxl` 读写，`xlrd` 读 `.xls`；仅公式重算才考虑 LibreOffice。
- **Word**：`python-docx` 读写；跨格式转换才用 `pandoc`。
- **PDF**：`pypdf`（合并/拆分）、`pdfplumber`（文本/表格抽取）、`reportlab`（生成）。
- **PowerPoint**：`python-pptx` 用于读取/抽取/检查/窄范围编辑；新建 PPT/PPTX 必须走 skill，不要直接用 `execute_code`+`python-pptx` 创建交付 PPT。

**Skill vs Sandbox**：数据抽取/格式转换/表格处理 → 沙箱；复杂版式/OOXML 精操作/模板化生成/公式重算 → 先加载 skill。
"""


# Single source of truth for the default sandbox / Python-execution block
# injected into the system prompt. ACP may build a per-session variant when a
# host marks the session as an existing project workspace.
SANDBOX_INFO_PROMPT = build_sandbox_info_prompt(use_output_dir=True)


# Minimal color constants used in status messages.
# The full ``Colors`` class lives in ``cli.py``; we only need a small subset.
class Colors:
    """Terminal color subset for tool-setup status messages."""

    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BRIGHT_CYAN = "\033[96m"
    DIM = "\033[2m"
    RESET = "\033[0m"


async def initialize_base_tools(config: Config, output=None, memory_manager=None, llm=None):
    """Initialize base tools (independent of workspace)

    These tools are loaded from package configuration and don't depend on workspace.
    Note: File tools are now workspace-dependent and initialized in add_workspace_tools()

    Args:
        config: Configuration object
        output: Callable for status messages (default: print). Pass a stderr
                writer when stdout must stay clean (e.g. ACP mode).
        memory_manager: Optional MemoryManager instance for memory tools.
        llm: Optional LLM client used to model-merge context memory writes.

    Returns:
        Tuple of (tools, skill_loader, mcp_task). The MCP task loads in the
        background — call ``await_mcp_tools(mcp_task)`` before running an
        agent turn to ensure MCP tools are available. ``mcp_task`` is
        ``None`` when MCP is disabled.
    """
    _out = output or print

    tools = []
    skill_loader = None

    # 0. Memory tools (cross-session, workspace-independent)
    if memory_manager is not None:
        tools.append(MemoryReadTool(memory_manager))
        tools.append(MemoryWriteTool(memory_manager, llm=llm))
        tools.append(MemorySearchTool(memory_manager))
        _out(f"{Colors.GREEN}✅ Loaded memory tools (memory_read, memory_write, memory_search){Colors.RESET}")

    # 1. Bash auxiliary tools (output monitoring and kill)
    # Note: BashTool itself is created in add_workspace_tools() with workspace_dir as cwd
    if config.tools.enable_bash:
        bash_output_tool = BashOutputTool()
        tools.append(bash_output_tool)
        _out(f"{Colors.GREEN}✅ Loaded Bash Output tool{Colors.RESET}")

        bash_kill_tool = BashKillTool()
        tools.append(bash_kill_tool)
        _out(f"{Colors.GREEN}✅ Loaded Bash Kill tool{Colors.RESET}")

    # 1b. Scheduled-task draft tool (workspace-independent).
    # Pops a pre-filled "create scheduled task" window on the desktop host via
    # ToolResult.raw_output → tool_call_update.rawOutput. Does not persist anything
    # itself; the renderer owns the actual save.
    tools.append(CreateScheduledTaskTool())
    _out(f"{Colors.GREEN}✅ Loaded Scheduled Task tool (create_scheduled_task){Colors.RESET}")

    # 2. Claude Skills (loaded from package directory)
    if config.tools.enable_skills:
        _out(f"{Colors.BRIGHT_CYAN}Loading Claude Skills...{Colors.RESET}")
        try:
            # Resolve builtin skills directory with priority search
            skills_path = Path(config.tools.skills_dir).expanduser()
            if skills_path.is_absolute():
                builtin_dir = skills_path
            else:
                # Search in priority order:
                # 1. Current directory (dev mode: ./skills or ./box_agent/skills)
                # 2. Package directory (installed: site-packages/box_agent/skills)
                search_paths = [
                    skills_path,  # ./skills for backward compatibility
                    Path("box_agent") / skills_path,  # ./box_agent/skills
                    Config.get_package_dir() / skills_path,  # site-packages/box_agent/skills
                ]

                builtin_dir = skills_path  # default
                for path in search_paths:
                    if path.exists():
                        builtin_dir = path.resolve()
                        break

            # User skills directory: ~/.box-agent/skills/
            # Auto-created so officev3 can drop new skills in and we pick them up on mtime change.
            user_skills_dir = Path.home() / ".box-agent" / "skills"
            user_skills_dir.mkdir(parents=True, exist_ok=True)

            # User skills take priority over builtin on name conflict
            sources = [
                (user_skills_dir, "user"),
                (builtin_dir, "builtin"),
            ]

            skill_tools, skill_loader = create_skill_tools(sources=sources)
            if skill_tools:
                tools.extend(skill_tools)
                _out(
                    f"{Colors.GREEN}✅ Loaded Skill tool (get_skill) — "
                    f"user: {user_skills_dir}, builtin: {builtin_dir}{Colors.RESET}"
                )
            else:
                _out(f"{Colors.YELLOW}⚠️  No available Skills found{Colors.RESET}")
        except Exception as e:
            _out(f"{Colors.YELLOW}⚠️  Failed to load Skills: {e}{Colors.RESET}")

    # 3. MCP tools (loaded with priority search, in background to avoid blocking startup)
    mcp_task: Optional[asyncio.Task] = None
    if config.tools.enable_mcp:
        mcp_config = config.tools.mcp
        set_mcp_timeout_config(
            connect_timeout=mcp_config.connect_timeout,
            execute_timeout=mcp_config.execute_timeout,
            sse_read_timeout=mcp_config.sse_read_timeout,
        )
        mcp_config_path = Config.find_config_file(config.tools.mcp_config_path)
        if mcp_config_path:
            _out(f"{Colors.BRIGHT_CYAN}Loading MCP tools in background (from: {mcp_config_path})...{Colors.RESET}")
            _out(
                f"{Colors.DIM}  MCP timeouts: connect={mcp_config.connect_timeout}s, "
                f"execute={mcp_config.execute_timeout}s, sse_read={mcp_config.sse_read_timeout}s{Colors.RESET}"
            )

            async def _load() -> List[Tool]:
                try:
                    loaded = await load_mcp_tools_async(str(mcp_config_path), auth_file=config.llm.auth_file)
                    if loaded:
                        _out(f"{Colors.GREEN}✅ Loaded {len(loaded)} MCP tools (from: {mcp_config_path}){Colors.RESET}")
                    else:
                        _out(f"{Colors.YELLOW}⚠️  No available MCP tools found{Colors.RESET}")
                    return loaded
                except Exception as e:
                    _out(f"{Colors.YELLOW}⚠️  Failed to load MCP tools: {e}{Colors.RESET}")
                    return []

            mcp_task = asyncio.create_task(_load(), name="mcp-background-load")
        else:
            _out(f"{Colors.YELLOW}⚠️  MCP config file not found: {config.tools.mcp_config_path}{Colors.RESET}")

    _out("")  # Empty line separator
    return tools, skill_loader, mcp_task


async def await_mcp_tools(mcp_task: Optional[asyncio.Task]) -> List[Tool]:
    """Await the background MCP loading task (no-op if already awaited or absent).

    Safe to call multiple times — asyncio.Task results are cached.
    Returns the list of loaded MCP tools, or [] if none/failed.
    """
    if mcp_task is None:
        return []
    try:
        return await mcp_task
    except Exception:
        return []


def register_mcp_tools(tool_map: dict[str, Tool], mcp_tools: list[Tool]) -> None:
    """Register MCP tools, allowing them to override same-named fallback tools."""
    for tool in mcp_tools:
        tool_map[tool.name] = tool


def merge_mcp_tools(base_tools: list[Tool], mcp_tools: list[Tool]) -> None:
    """Merge MCP tools into a tool list, replacing same-named fallback tools."""
    mcp_by_name = {tool.name: tool for tool in mcp_tools}
    if not mcp_by_name:
        return

    replaced_names: set[str] = set()
    for index, tool in enumerate(base_tools):
        replacement = mcp_by_name.get(tool.name)
        if replacement is not None:
            base_tools[index] = replacement
            replaced_names.add(tool.name)

    for tool in mcp_tools:
        if tool.name not in replaced_names:
            base_tools.append(tool)


def add_workspace_tools(tools: List[Tool], config: Config, workspace_dir: Path, sandbox_mode: bool = False,
                        allow_full_access: bool = True, non_interactive: bool = False, output=None,
                        llm=None, permission_engine: PermissionEngine | None = None,
                        skill_runtime_context: SkillRuntimeContext | None = None,
                        use_output_dir: bool = True,
                        artifact_root_dir: str | Path | None = None,
                        env_context=None):
    """Add workspace-dependent tools

    These tools need to know the workspace directory.

    Args:
        tools: Existing tools list to add to
        config: Configuration object
        workspace_dir: Workspace directory path
        sandbox_mode: If True, enable Jupyter sandbox mode
        allow_full_access: If True, tools can access full system; if False, restricted to workspace
        non_interactive: If True, bash never prompts on stdin; dangerous
            commands return approval requests for the core/host.
        output: Callable for status messages (default: print)
        llm: LLM client instance (needed for sub_agent tool)
        permission_engine: If provided, tools use capability-based permission checks
        skill_runtime_context: Runtime env to expose to subprocess-backed tools
        use_output_dir: If True, execute_code chdirs into {workspace}/output.
        artifact_root_dir: Optional host-supplied output root for this session.
    """
    _out = output or print
    # Ensure workspace directory exists
    workspace_dir.mkdir(parents=True, exist_ok=True)
    artifact_root = Path(artifact_root_dir).expanduser().resolve() if use_output_dir and artifact_root_dir else None

    # Bash tool - needs workspace as cwd for command execution
    runtime_context = skill_runtime_context or build_skill_runtime_context(sandbox_mode=sandbox_mode)
    if config.tools.enable_bash:
        sandbox_venv_path = None
        if sandbox_mode and not getattr(sys, "frozen", False):
            sandbox_venv_path = str(SandboxEnvironment().venv_dir)
        bash_tool = BashTool(
            workspace_dir=str(workspace_dir),
            allow_full_access=allow_full_access,
            non_interactive=non_interactive,
            sandbox_venv_path=sandbox_venv_path,
            permission_engine=permission_engine,
            runtime_env=runtime_context.env(),
        )
        tools.append(bash_tool)
        _out(f"{Colors.GREEN}✅ Loaded Bash tool (cwd: {workspace_dir}){Colors.RESET}")

    # File tools - need workspace to resolve relative paths
    if config.tools.enable_file_tools:
        tools.extend(
            [
                ReadTool(workspace_dir=str(workspace_dir), allow_full_access=allow_full_access, permission_engine=permission_engine),
                WriteTool(workspace_dir=str(workspace_dir), allow_full_access=allow_full_access, permission_engine=permission_engine),
                EditTool(workspace_dir=str(workspace_dir), allow_full_access=allow_full_access, permission_engine=permission_engine),
            ]
        )
        _out(f"{Colors.GREEN}✅ Loaded file operation tools (workspace: {workspace_dir}){Colors.RESET}")

    # Todo tool - task tracking for multi-step workflows
    if config.tools.enable_todo:
        store = TodoStore()
        tools.append(TodoWriteTool(store))
        tools.append(TodoReadTool(store))
        _out(f"{Colors.GREEN}✅ Loaded todo tools (todo_write, todo_read){Colors.RESET}")

    # Plan tool - user-visible approach/scope/verification snapshots
    if getattr(config.tools, "enable_plan", True):
        store = PlanStore()
        tools.append(PlanWriteTool(store))
        tools.append(PlanReadTool(store))
        _out(f"{Colors.GREEN}✅ Loaded plan tools (plan_write, plan_read){Colors.RESET}")

    # Jupyter sandbox tool - Python code execution environment
    if sandbox_mode:
        sandbox_tool = JupyterSandboxTool(
            workspace_dir=str(workspace_dir),
            runtime_env=runtime_context.env(),
            use_output_dir=use_output_dir,
            output_dir=str(artifact_root) if artifact_root else None,
        )
        tools.append(sandbox_tool)
        # Also add sandbox status tool
        status_tool = SandboxStatusTool()
        SandboxStatusTool.set_sandbox_tool(sandbox_tool)
        tools.append(status_tool)
        _out(f"{Colors.GREEN}✅ Loaded Jupyter sandbox tool (execute_code){Colors.RESET}")
        _out(f"{Colors.GREEN}✅ Loaded sandbox status tool{Colors.RESET}")

    # Vision review tool — reads local screenshots and sends image content to the current LLM
    if llm is not None:
        tools.append(
            VisionReviewTool(
                llm=llm,
                workspace_dir=str(workspace_dir),
                allow_full_access=allow_full_access,
                permission_engine=permission_engine,
            )
        )
        _out(f"{Colors.GREEN}✅ Loaded vision review tool (vision_review){Colors.RESET}")

    # Image generation tool — saves host-generated bitmap assets into the workspace
    image_generation_config = getattr(config, "image_generation", None)
    tools.append(
        GenerateImageTool(
            workspace_dir=str(workspace_dir),
            output_dir=str(artifact_root) if artifact_root else None,
            allow_full_access=allow_full_access,
            permission_engine=permission_engine,
            endpoint=getattr(image_generation_config, "endpoint", "") or None,
            api_key=getattr(image_generation_config, "api_key", "") or None,
            model=getattr(image_generation_config, "model", "") or None,
            auth_file=(
                getattr(image_generation_config, "auth_file", "")
                or getattr(getattr(config, "llm", None), "auth_file", "")
            ),
            timeout=getattr(image_generation_config, "timeout", None),
        )
    )
    _out(f"{Colors.GREEN}✅ Loaded image generation tool (generate_image){Colors.RESET}")

    # Obsidian tools — host/Vault dependent, so register with workspace tools
    # before sub-agent so child agents inherit the native Obsidian capability.
    obsidian_tools = create_obsidian_tools(env_context=env_context)
    tools.extend(obsidian_tools)
    _out(f"{Colors.GREEN}✅ Loaded Obsidian tools (obsidian_create_note, obsidian_update_note, obsidian_daily_note){Colors.RESET}")

    # Sub-agent tool — must be registered last so it can reference all other tools
    if config.tools.enable_sub_agent and llm is not None:
        parent_tools = {t.name: t for t in tools}
        sub_agent_tool = SubAgentTool(
            llm=llm,
            parent_tools=parent_tools,
            workspace_dir=str(workspace_dir),
            artifact_detection_enabled=use_output_dir,
            artifact_root_dir=str(artifact_root) if artifact_root else None,
        )
        tools.append(sub_agent_tool)
        _out(f"{Colors.GREEN}✅ Loaded sub-agent tool (sub_agent){Colors.RESET}")
