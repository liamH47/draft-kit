"""The registry must describe reality, not a hand-kept list that drifts.

Its whole value is being the single place to look for "where does our data come
from" — which is worthless the moment it disagrees with the adapters.
"""

import pkgutil

import pytest

import draftkit.sources as sources_package
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import registry

KINDS = {
    "identity",
    "projection",
    "market",
    "platform",
    "expert",
    "buzz",
    "crosswalk",
    "league",
}
AUTH_KINDS = {"none", "oauth", "extension"}


def test_every_adapter_module_appears_in_the_registry():
    """The check that stops the registry going stale: a new adapter shows up
    here without anyone remembering to register it."""
    modules = {
        m.name
        for m in pkgutil.iter_modules(sources_package.__path__)
        if m.name not in {"base", "registry"}
    }
    assert {info.module.__name__.rsplit(".", 1)[-1] for info in registry.all_sources()} == modules


def test_every_entry_is_complete_and_well_formed():
    for info in registry.all_sources():
        assert info.kind in KINDS, f"{info.name} has an unknown kind"
        assert info.auth in AUTH_KINDS, f"{info.name} has an unknown auth kind"
        assert info.homepage.startswith("http"), f"{info.name} needs a homepage"
        assert info.attribution.strip(), f"{info.name} needs an attribution line"
        assert info.provides, f"{info.name} declares no fields"
        assert info.ttl.total_seconds() > 0, f"{info.name} needs a refresh interval"


def test_source_names_are_unique():
    names = [info.name for info in registry.all_sources()]
    assert len(names) == len(set(names))


def test_every_adapter_satisfies_the_protocol():
    for info in registry.all_sources():
        assert callable(info.module.request)
        assert callable(info.module.validate)
        assert callable(info.module.parse)


def test_lookup_by_name():
    assert registry.by_name("espn_market").kind == "platform"
    with pytest.raises(KeyError):
        registry.by_name("no_such_source")


def test_attributions_cover_every_source():
    assert len(registry.attributions()) == len(registry.all_sources())


def test_generated_markdown_lists_everything():
    doc = registry.as_markdown()
    for info in registry.all_sources():
        assert info.title in doc
        assert info.homepage in doc
    # And it explains what we deliberately do not use.
    assert "FantasyPros" in doc
    assert "Yahoo" in doc


def test_as_dict_is_json_friendly():
    entry = registry.by_name("ffcalc").as_dict()
    assert entry["ttl_hours"] == 3.0
    assert isinstance(entry["provides"], list)


def test_registry_modules_are_the_ones_the_store_can_fetch(tmp_path, fixture_fetcher):
    """Registry entries are not documentation — they are the live adapters."""
    store = SnapshotStore(tmp_path, fixture_fetcher)
    params = {
        "sleeper_players": {},
        "sleeper_projections": {"season": 2026},
        "dp_playerids": {},
        "ffcalc": {"format": "half_ppr", "teams": 12, "year": 2026},
        "borischen": {"format": "half_ppr"},
        "espn_market": {"season": 2026},
        "espn_league": {"season": 2026, "league_id": "1234567"},
        "espn_projections": {"season": 2026},
        "cbs_rankings": {"format": "ppr"},
        "fantasypros": {"format": "half_ppr"},
        "yahoo_adp": {"start": 0},
        "mfl_adp": {"format": "half_ppr", "year": 2026},
        "sleeper_trending": {"kind": "add"},
    }
    for info in registry.all_sources():
        dataset, _ = store.get(info.module, params[info.name])
        assert dataset.rows, f"{info.name} parsed no rows"


def test_every_registered_source_is_warmed_before_a_draft():
    """The registry auto-discovers adapters; the warm script does not.

    scripts/warm_snapshots.py carries a hand-written job list, so a new source
    is discovered by the registry (and appears in the docs) while being absent
    from the warm — and that gap only shows up on draft morning. draftday mode
    warms every source and then pins to disk with DRAFTKIT_OFFLINE=1; a source
    that was never warmed has no snapshot to be pinned to, so the first board
    read of the draft goes to the network with a pick clock running.

    Matching on the imported module names rather than on the jobs list itself,
    because the list is built at runtime from league team counts.
    """
    import ast
    from pathlib import Path

    import draftkit.sources.registry as registry_module

    script = Path(registry_module.__file__).parent.parent.parent.parent / "scripts"
    tree = ast.parse((script / "warm_snapshots.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "draftkit.sources"
        for alias in node.names
    }
    # The registry keys by adapter `name`; the warm script imports by MODULE.
    modules = {info.module.__name__.rsplit(".", 1)[-1] for info in registry.all_sources()}
    # espn_league is a per-league settings read, not a pre-draft feed: it is
    # fetched by the import endpoint on demand and has nothing to warm.
    missing = modules - imported - {"espn_league"}
    assert not missing, (
        f"these sources are registered but never warmed: {sorted(missing)} — "
        "add them to the jobs list in scripts/warm_snapshots.py"
    )
