"""Compatibility imports for the host-neutral project context builder.

Project startup context is shared by ACP and CLI. Keep this module as a
stable import path for integrations that used the historical ACP location.
"""

import subprocess
from pathlib import Path

from box_agent.project_context import (
    _GIT_TIMEOUT_SECONDS,
    _MAX_AGENTS_CHARS,
    _MAX_STATUS_LINES,
    _read_agents_md,
    _run_git,
    _truncate_text,
    append_prompt_segment,
    build_project_startup_context_prompt,
    replace_prompt_placeholders,
)
