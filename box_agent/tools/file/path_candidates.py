"""Bounded structural candidates for unresolved user paths."""

from __future__ import annotations

from pathlib import Path


MAX_HOME_PATH_CANDIDATES = 3


def home_relative_path_candidates(
    raw_path: str,
    *,
    home_dir: Path | None = None,
    active_roots: tuple[Path, ...] = (),
) -> list[dict[str, object]]:
    """Return existing paths whose first component matches a Home child.

    Matching is structural and case-insensitive. Only Home's immediate
    children are inspected; candidates are never executed or authorized here.
    """
    stripped = raw_path.strip()
    supplied = Path(stripped)
    if not stripped or stripped.startswith("~") or ".." in supplied.parts:
        return []

    unresolved_paths: list[Path] = []
    if supplied.is_absolute():
        for root in active_roots:
            try:
                unresolved_paths.append(supplied.relative_to(root.expanduser().absolute()))
            except ValueError:
                continue
    else:
        unresolved_paths.append(supplied)
    if not unresolved_paths:
        return []

    home = (home_dir or Path.home()).expanduser().absolute()
    try:
        children = sorted(home.iterdir(), key=lambda child: child.name.casefold())
    except OSError:
        return []

    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for unresolved in unresolved_paths:
        if not unresolved.parts:
            continue
        first_component = unresolved.parts[0].casefold()
        remaining = unresolved.parts[1:]
        for child in children:
            if child.name.casefold() != first_component:
                continue
            candidate = child.joinpath(*remaining)
            try:
                exists = candidate.exists()
            except OSError:
                continue
            candidate_key = str(candidate)
            if not exists or candidate_key in seen:
                continue
            seen.add(candidate_key)
            candidates.append(
                {
                    "path": candidate_key,
                    "basis": "home_child_case_insensitive_match",
                    "exists": True,
                }
            )
            if len(candidates) >= MAX_HOME_PATH_CANDIDATES:
                return candidates
    return candidates
