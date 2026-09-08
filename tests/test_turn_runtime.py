from __future__ import annotations

from box_agent.turn_runtime import sync_skill_cache_fingerprint_context


def test_sync_skill_cache_fingerprint_context_copies_skill_names() -> None:
    cache_context: dict[str, object] = {
        "unrelated": "keep",
    }
    matched = (name for name in ("alpha", "beta"))
    preloaded = ["alpha"]

    sync_skill_cache_fingerprint_context(
        cache_context,
        matched_skill_names=matched,
        preloaded_skill_names=preloaded,
    )

    assert cache_context == {
        "unrelated": "keep",
        "filtered_skill_names": ["alpha", "beta"],
        "preloaded_skill_names": ["alpha"],
    }
