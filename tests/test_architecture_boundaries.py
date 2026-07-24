"""Executable dependency rules for the three-layer architecture."""

from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "box_agent"
CORE_BRIDGE = Path("runtime.py")
APPLICATION_ADAPTER_MODULES = ("box_agent.acp", "box_agent.cli", "acp", "cli")
STABLE_KERNEL_MODULES = (
    Path("core.py"),
    Path("loop_guards.py"),
    Path("workflow_policy.py"),
)
PRESENTATION_WORKFLOW_TOKENS = (
    "controlled_presentation",
    "presentation_research_mode",
    "controlled_presentation_stage",
    "pptx",
    "powerpoint",
    "slide deck",
    "演示文稿",
    "幻灯片",
)


def _direct_core_imports(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name == "box_agent.core"
                or alias.name.startswith("box_agent.core.")
                for alias in node.names
            ):
                violations.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if (
                module == "box_agent.core"
                or module.startswith("box_agent.core.")
                or (node.level > 0 and (module == "core" or module.startswith("core.")))
                or (
                    module == "box_agent"
                    and any(alias.name == "core" for alias in node.names)
                )
                or (
                    node.level > 0
                    and not module
                    and any(alias.name == "core" for alias in node.names)
                )
            ):
                violations.append(node.lineno)
    return violations


def _is_application_adapter_module(name: str) -> bool:
    return any(
        name == module or name.startswith(f"{module}.")
        for module in APPLICATION_ADAPTER_MODULES
    )


def _application_adapter_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [module] if module else []
            if module in {"", "box_agent"}:
                names.extend(alias.name for alias in node.names)
        else:
            continue
        for name in names:
            if _is_application_adapter_module(name):
                violations.append(f"{name}:{node.lineno}")
    return violations


def test_only_runtime_bridge_imports_core_implementation() -> None:
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative_path = path.relative_to(PACKAGE_ROOT)
        if relative_path in {CORE_BRIDGE, Path("core.py")}:
            continue
        for lineno in _direct_core_imports(path):
            violations.append(f"{relative_path}:{lineno}")

    assert violations == [], (
        "Application and capability modules must use Agent/run_events, "
        "box_agent.runtime, artifacts, or policy modules instead of importing "
        f"box_agent.core directly: {violations}"
    )


def test_core_does_not_depend_on_application_adapters() -> None:
    core_path = PACKAGE_ROOT / "core.py"
    forbidden = _application_adapter_imports(core_path)
    assert forbidden == [], f"Core must not import application adapters: {forbidden}"


def test_core_depends_on_workflow_contract_not_implementations() -> None:
    core_path = PACKAGE_ROOT / "core.py"
    tree = ast.parse(core_path.read_text(encoding="utf-8"), filename=str(core_path))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.append(module)
            if module in {"", "box_agent"}:
                imported_modules.extend(alias.name for alias in node.names)

    assert not any(
        module == "box_agent.workflows"
        or module.startswith("box_agent.workflows.")
        or module == "workflows"
        or module.startswith("workflows.")
        for module in imported_modules
    ), "Core must depend on WorkflowPolicy, not a concrete workflow package"

    source = core_path.read_text(encoding="utf-8")
    assert "controlled_presentation" not in source
    assert "WorkflowPolicy" in source


def test_stable_kernel_contains_no_concrete_presentation_workflow() -> None:
    violations: list[str] = []
    for relative_path in STABLE_KERNEL_MODULES:
        path = PACKAGE_ROOT / relative_path
        source = path.read_text(encoding="utf-8").lower()
        for token in PRESENTATION_WORKFLOW_TOKENS:
            if token in source:
                violations.append(f"{relative_path}:{token}")

    assert violations == [], (
        "Concrete PPT routing and checkpoint state belong under "
        f"box_agent.workflows, not the stable kernel: {violations}"
    )


def test_acp_depends_on_generic_workflow_lifecycle_only() -> None:
    acp_path = PACKAGE_ROOT / "acp" / "__init__.py"
    tree = ast.parse(acp_path.read_text(encoding="utf-8"), filename=str(acp_path))
    concrete_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            continue
        concrete_imports.extend(
            module
            for module in modules
            if module.startswith("box_agent.workflows.presentation_")
        )

    source = acp_path.read_text(encoding="utf-8")
    assert concrete_imports == []
    assert '"controlled_presentation"' not in source


def test_application_adapter_detector_rejects_submodule_imports(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "forbidden_imports.py"
    sample.write_text(
        "import box_agent.acp.session\n"
        "from box_agent.acp.protocol import Request\n"
        "from .acp.transport import Connection\n"
        "from box_agent import cli\n"
        "from . import acp\n",
        encoding="utf-8",
    )

    assert _application_adapter_imports(sample) == [
        "box_agent.acp.session:1",
        "box_agent.acp.protocol:2",
        "acp.transport:3",
        "cli:4",
        "acp:5",
    ]
