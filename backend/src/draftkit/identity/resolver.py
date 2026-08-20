"""Resolve source-native identities to the canonical Sleeper player_id.

Chain (first hit wins):
  1. overrides.yaml — manual fixes, checked into git
  2. exact match on normalized name + position + team
  3. match on normalized name + position (low confidence)

The dynastyprocess crosswalk feeds the index too (its merge_name catches
spellings Sleeper doesn't use), and later provides espn_id/yahoo_id joins.
Unresolved names are collected, not dropped, so /api/admin/unmatched can show
what needs an override before draft day.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from draftkit.identity.normalize import normalize_name
from draftkit.identity.teams import canonical_team, team_from_defense_name


@dataclass
class Resolution:
    sleeper_id: str | None
    confidence: str  # "override" | "exact" | "name_pos" | "unmatched"


@dataclass
class Resolver:
    _by_name_pos_team: dict[tuple[str, str, str], str] = field(default_factory=dict)
    _by_name_pos: dict[tuple[str, str], str | None] = field(default_factory=dict)
    _overrides: dict[str, str] = field(default_factory=dict)
    # team abbreviation -> the defense's canonical id
    _defense_ids: dict[str, str] = field(default_factory=dict)
    unmatched: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        players: list[dict[str, Any]],
        crosswalk: list[dict[str, Any]] | None = None,
        overrides_path: Path | None = None,
    ) -> "Resolver":
        r = cls()
        for p in players:
            if p["position"] == "DEF":
                # Sleeper keys defenses by team abbreviation, which makes the
                # team code the canonical id at no cost.
                abbr = canonical_team(p.get("team")) or team_from_defense_name(p["name"])
                if abbr:
                    r._defense_ids.setdefault(abbr, p["sleeper_id"])
                continue
            r._index(p["name"], p["position"], canonical_team(p.get("team")), p["sleeper_id"])
        for row in crosswalk or []:
            for key in ("name", "merge_name"):
                if row.get(key):
                    r._index(
                        row[key],
                        row.get("position", ""),
                        canonical_team(row.get("team")),
                        row["sleeper_id"],
                    )
        if overrides_path and overrides_path.is_file():
            loaded = yaml.safe_load(overrides_path.read_text()) or {}
            r._overrides = {normalize_name(k): str(v) for k, v in loaded.items()}
        return r

    def _index(self, name: str, position: str, team: str | None, sleeper_id: str) -> None:
        norm = normalize_name(name)
        if team:
            self._by_name_pos_team.setdefault((norm, position, team), sleeper_id)
        key = (norm, position)
        if key in self._by_name_pos and self._by_name_pos[key] != sleeper_id:
            # Two different players share name+position: poison the key so we
            # never guess wrong (e.g. two Josh Allens). Team match still works.
            self._by_name_pos[key] = None
        else:
            self._by_name_pos.setdefault(key, sleeper_id)

    def resolve(self, name: str, position: str, team: str | None = None) -> Resolution:
        norm = normalize_name(name)
        if norm in self._overrides:
            return Resolution(self._overrides[norm], "override")

        # Defenses have no id in any crosswalk and a different name in every
        # feed, but they always denote a team — so resolve the team instead.
        if position == "DEF":
            abbr = canonical_team(team) or team_from_defense_name(name)
            if abbr and abbr in self._defense_ids:
                return Resolution(self._defense_ids[abbr], "team")
            self.unmatched.append({"name": name, "position": position, "team": team})
            return Resolution(None, "unmatched")

        team = canonical_team(team) or team
        if team and (hit := self._by_name_pos_team.get((norm, position, team))):
            return Resolution(hit, "exact")
        hit = self._by_name_pos.get((norm, position))
        if hit:
            return Resolution(hit, "name_pos")
        self.unmatched.append({"name": name, "position": position, "team": team})
        return Resolution(None, "unmatched")
