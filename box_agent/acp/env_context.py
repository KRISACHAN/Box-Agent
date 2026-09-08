"""Compatibility imports for the shared environment-context renderer.

The environment metadata contract is host-neutral even though ACP introduced
it.  Keep this module as a stable import path for ACP clients and integrations
while the implementation lives at :mod:`box_agent.env_context`.
"""

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from box_agent.env_context import (
    _KNOWN_TOP_LEVEL_KEYS,
    _MAX_NAME_LEN,
    _MAX_PATH_LEN,
    _MAX_PLATFORM_LEN,
    _PLATFORM_ALLOWED_CHARS,
    _format_browser_connector,
    _format_browser_tools,
    _format_cli_section,
    _format_hyperframes,
    _format_image_service,
    _format_obsidian,
    _has_unsafe_chars,
    _is_absolute_path,
    _sanitize_cli,
    _sanitize_hyperframes,
    _sanitize_label,
    _sanitize_obsidian,
    _sanitize_path,
    _sanitize_platform,
    _sanitize_provider,
    _sanitize_runtimes,
    BrowserConnectorState,
    BrowserToolsState,
    EnvContext,
    HostRuntime,
    HyperFramesState,
    ImageServiceState,
    ObsidianState,
    build_env_context_prompt,
    logger,
)
