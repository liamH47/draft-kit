"""The registry must describe reality, not a hand-kept list that drifts.

Its whole value is being the single place to look for "where does our data come
from" — which is worthless the moment it disagrees with the adapters.
"""

import pkgutil

import pytest

import draftkit.sources as sources_package
from draftkit.snapshots.store import SnapshotStore
from draftkit.sources import registry

KINDS = {"identity", "projection", "market", "platform", "expert", "crosswalk", "league"}
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
    }
    for info in registry.all_sources():
        dataset, _ = store.get(info.module, params[info.name])
        assert dataset.rows, f"{info.name} parsed no rows"
