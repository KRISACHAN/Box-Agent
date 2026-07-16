"""Tests for Phase 1: ContextEntry metadata format on CONTEXT.md.

Covers:
- New-format roundtrip preserves metadata
- Legacy line-based file migrates on first write
- ``search`` increments hits and bumps last_used
- ``apply_context_operations`` preserves metadata for untouched entries
- ``append_context`` keeps existing entries' hits
"""

from __future__ import annotations

from pathlib import Path

import pytest

from box_agent.memory import (
    ContextEntry,
    MemoryManager,
    _new_entry,
    _now_iso,
    parse_context_file,
    write_context_file,
)


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    d = tmp_path / "memory"
    d.mkdir()
    return d


@pytest.fixture
def mgr(memory_dir: Path) -> MemoryManager:
    return MemoryManager(memory_dir=str(memory_dir))


# ── New-format roundtrip ─────────────────────────────────────


def test_new_format_roundtrip(memory_dir: Path):
    path = memory_dir / "CONTEXT.md"
    entries = [
        ContextEntry(
            id="ctx_test_1",
            content="- alpha",
            created="2026-05-17T10:00:00",
            last_used="2026-05-17T10:00:00",
            hits=2,
            source="tool",
            confidence=0.9,
            session_id="office-session-1",
            turn_id="turn-7",
            trigger="loop_end",
        ),
        ContextEntry(
            id="ctx_test_2",
            content="- beta\n- multi-line continued",
            created="2026-05-17T11:00:00",
            last_used="2026-05-17T12:00:00",
            hits=0,
            source="extractor",
            confidence=0.7,
        ),
    ]
    write_context_file(path, entries)
    raw = path.read_text(encoding="utf-8")
    assert "session_id=office-session-1" in raw
    assert "turn_id=turn-7" in raw
    assert "trigger=loop_end" in raw

    parsed = parse_context_file(path)
    assert len(parsed) == 2
    assert parsed[0].id == "ctx_test_1"
    assert parsed[0].content == "- alpha"
    assert parsed[0].hits == 2
    assert parsed[0].source == "tool"
    assert parsed[0].confidence == 0.9
    assert parsed[0].session_id == "office-session-1"
    assert parsed[0].turn_id == "turn-7"
    assert parsed[0].trigger == "loop_end"
    assert parsed[1].id == "ctx_test_2"
    assert parsed[1].content == "- beta\n- multi-line continued"
    assert parsed[1].source == "extractor"
    assert parsed[1].turn_id == ""


def test_write_empty_entries_truncates_file(memory_dir: Path):
    path = memory_dir / "CONTEXT.md"
    path.write_text("preexisting\n", encoding="utf-8")
    write_context_file(path, [])
    assert path.read_text(encoding="utf-8") == ""


# ── Legacy migration ────────────────────────────────────────


def test_legacy_file_parses_each_line_as_entry(memory_dir: Path):
    path = memory_dir / "CONTEXT.md"
    path.write_text("- legacy fact one\n- legacy fact two\n\n", encoding="utf-8")

    entries = parse_context_file(path)
    assert len(entries) == 2
    assert entries[0].content == "- legacy fact one"
    assert entries[0].source == "legacy"
    assert entries[0].hits == 0
    assert entries[1].content == "- legacy fact two"


def test_legacy_file_upgrades_on_first_write(mgr: MemoryManager):
    mgr.context_file.write_text("- legacy one\n- legacy two\n", encoding="utf-8")

    # Trigger a write via append (legacy lines are loaded, new line appended)
    mgr.append_context("- fresh fact")

    raw = mgr.context_file.read_text(encoding="utf-8")
    assert "<!-- ctx" in raw, "file should be upgraded to new format"
    assert raw.count("<!-- ctx") == 3

    # read_context() still returns plain text equivalent
    assert "- legacy one" in mgr.read_context()
    assert "- legacy two" in mgr.read_context()
    assert "- fresh fact" in mgr.read_context()


def test_legacy_file_read_through_manager(mgr: MemoryManager):
    mgr.context_file.write_text("- alpha\n- beta\n", encoding="utf-8")
    assert mgr.read_context() == "- alpha\n- beta"


# ── Search updates hits/last_used ───────────────────────────


def test_search_increments_hits(mgr: MemoryManager):
    mgr.write_context("- Q2 goal: dashboard")
    entries_before = parse_context_file(mgr.context_file)
    assert entries_before[0].hits == 0
    original_id = entries_before[0].id

    matches = mgr.search("Q2")
    assert matches == ["- Q2 goal: dashboard"]

    entries_after = parse_context_file(mgr.context_file)
    assert len(entries_after) == 1
    assert entries_after[0].id == original_id, "id must be stable across hits update"
    assert entries_after[0].hits == 1
    assert entries_after[0].last_used >= entries_after[0].created


def test_search_no_match_does_not_bump_hits(mgr: MemoryManager):
    mgr.write_context("- only entry")
    mgr.search("nonexistent_term_xyz")

    entries = parse_context_file(mgr.context_file)
    assert entries[0].hits == 0


def test_search_increments_hits_repeatedly(mgr: MemoryManager):
    mgr.write_context("- repeat me")
    for _ in range(3):
        mgr.search("repeat")

    entries = parse_context_file(mgr.context_file)
    assert entries[0].hits == 3


# ── Metadata survives apply_context_operations ──────────────


def test_apply_operations_preserves_untouched_entry_hits(mgr: MemoryManager):
    mgr.write_context("- entry one\n- entry two")
    mgr.search("entry one")  # bump hits on entry one
    mgr.search("entry one")

    entries_before = parse_context_file(mgr.context_file)
    one_before = next(e for e in entries_before if e.content == "- entry one")
    assert one_before.hits == 2

    mgr.apply_context_operations([
        {"action": "add", "content": "- entry three"},
    ])

    entries_after = parse_context_file(mgr.context_file)
    one_after = next(e for e in entries_after if e.content == "- entry one")
    assert one_after.id == one_before.id
    assert one_after.hits == 2, "untouched entries must keep their hit counts"
    assert any(e.content == "- entry three" for e in entries_after)


def test_apply_operations_replace_bumps_last_used(mgr: MemoryManager):
    mgr.write_context("- old fact")
    entries = parse_context_file(mgr.context_file)
    original_id = entries[0].id
    original_created = entries[0].created

    mgr.apply_context_operations([
        {"action": "replace", "old": "- old fact", "new": "- new fact"},
    ])

    entries = parse_context_file(mgr.context_file)
    assert len(entries) == 1
    assert entries[0].content == "- new fact"
    assert entries[0].id == original_id, "id should be stable across replace"
    assert entries[0].created == original_created, "created should not change on replace"


def test_append_preserves_existing_metadata(mgr: MemoryManager):
    mgr.write_context("- existing fact")
    mgr.search("existing")
    entries_before = parse_context_file(mgr.context_file)
    assert entries_before[0].hits == 1
    original_id = entries_before[0].id

    mgr.append_context("- new fact")

    entries_after = parse_context_file(mgr.context_file)
    assert len(entries_after) == 2
    existing = next(e for e in entries_after if e.content == "- existing fact")
    assert existing.id == original_id
    assert existing.hits == 1


# ── Helper sanity ───────────────────────────────────────────


def test_new_entry_has_unique_ids():
    a = _new_entry("- a")
    b = _new_entry("- b")
    assert a.id != b.id
    assert a.id.startswith("ctx_")
    assert a.created == a.last_used
    assert a.hits == 0


def test_now_iso_is_second_precision():
    stamp = _now_iso()
    assert "T" in stamp
    assert len(stamp) == 19  # YYYY-MM-DDTHH:MM:SS


# ── Topic sharding ──────────────────────────────────────────


def test_append_context_routes_to_named_topic(mgr: MemoryManager):
    mgr.append_context("- preference: dark mode", topic="preferences")
    mgr.append_context("- uses pytest", topic="testing")

    assert sorted(mgr.list_topics()) == ["preferences", "testing"]
    assert "dark mode" in mgr.read_context_topic("preferences")
    assert "pytest" in mgr.read_context_topic("testing")
    assert "dark mode" not in mgr.read_context_topic("testing")


def test_write_context_overwrites_only_target_topic(mgr: MemoryManager):
    mgr.append_context("- a", topic="alpha")
    mgr.append_context("- b", topic="beta")

    mgr.write_context("- a2", topic="alpha")

    assert mgr.read_context_topic("alpha") == "- a2"
    assert mgr.read_context_topic("beta") == "- b"


def test_topic_slug_normalizes_unsafe_chars(mgr: MemoryManager):
    mgr.append_context("- thing", topic="Project X / Module.A")
    topics = mgr.list_topics()
    assert len(topics) == 1
    # slashes/spaces/dots collapse into a single dash run
    assert "/" not in topics[0]
    assert "." not in topics[0]


def test_legacy_context_file_is_preserved_for_search_fallback(memory_dir: Path):
    legacy = memory_dir / "CONTEXT.md"
    legacy.write_text("- old line\n", encoding="utf-8")

    mgr = MemoryManager(memory_dir=str(memory_dir))

    assert legacy.exists()
    assert mgr.search("old") == ["- old line"]
    assert not (memory_dir / "trash").exists()
    assert mgr.v2_state_file.exists()


def test_topic_store_writes_sidecar_index(mgr: MemoryManager):
    mgr.append_context("- one", topic="alpha")
    mgr.append_context("- two\n- three", topic="beta")

    index_path = mgr.context_dir / "_index.json"
    assert index_path.exists()
    import json as _json
    data = _json.loads(index_path.read_text(encoding="utf-8"))
    assert data["alpha"]["count"] == 1
    assert data["beta"]["count"] == 2
    assert "one" in data["alpha"]["terms"]
    assert "three" in data["beta"]["terms"]


def test_write_all_context_entries_refreshes_memory_summary(mgr: MemoryManager):
    mgr.write_all_context_entries([
        _new_entry("- project uses uv", topic="project"),
    ])

    summary = mgr.memory_summary_file.read_text(encoding="utf-8")
    assert "`project`" in summary
    assert "uses" in summary


def test_memory_manager_leaves_legacy_context_index_untouched(memory_dir: Path):
    context_dir = memory_dir / "context"
    context_dir.mkdir()
    entry = _new_entry("- user prefers dark mode", topic="preferences")
    write_context_file(context_dir / "preferences.md", [entry])
    (context_dir / "_index.json").write_text(
        '{"preferences": {"count": 1, "hits_total": 0}}\n',
        encoding="utf-8",
    )

    mgr = MemoryManager(memory_dir=str(memory_dir))

    import json as _json
    data = _json.loads((context_dir / "_index.json").read_text(encoding="utf-8"))
    assert "terms" not in data["preferences"]
    assert mgr.search("dark mode") == ["- user prefers dark mode"]


def test_search_routes_to_indexed_topic_without_reading_unrelated_topic(mgr: MemoryManager, monkeypatch):
    mgr.append_context("- user prefers dark mode", topic="preferences")
    mgr.append_context("- project dashboard status", topic="project")

    calls: list[str] = []
    original = mgr.topic_store.read_topic

    def wrapped(topic: str):
        calls.append(topic)
        return original(topic)

    monkeypatch.setattr(mgr.topic_store, "read_topic", wrapped)

    results = mgr.search("dark mode")

    assert results == ["- user prefers dark mode"]
    assert calls == ["preferences"]


def test_search_falls_back_to_all_topics_when_index_is_stale(mgr: MemoryManager):
    mgr.append_context("- user prefers dark mode", topic="preferences")
    mgr.append_context("- project dashboard status", topic="project")
    mgr.topic_store.index_file.write_text(
        '{"preferences": {"count": 1}, "project": {"count": 1}}\n',
        encoding="utf-8",
    )

    results = mgr.search("dark mode")

    assert results == ["- user prefers dark mode"]


def test_search_can_be_scoped_to_explicit_topic(mgr: MemoryManager):
    mgr.append_context("- PPT style: dark editorial", topic="preferences")
    mgr.append_context("- PPT project: Brazil world cup deck", topic="project")

    results = mgr.search("ppt", topic="project")

    assert results == ["- PPT project: Brazil world cup deck"]
