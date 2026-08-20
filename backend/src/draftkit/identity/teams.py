"""NFL team identity, which is how defenses get resolved.

Defenses have no player id anywhere useful: the DynastyProcess crosswalk
carries zero DST rows, so there is nothing to join on. What every source does
agree on is the team — they just spell it differently:

    Sleeper   "San Francisco 49ers"   player_id "SF"
    FFC       "San Francisco Defense"
    ESPN      "49ers D/ST"
    crosswalk "SFO" (and GBP, KCC, NEP, NOS, JAC, LVR...)

So a defense is resolved by working out which team it is, rather than by
matching a name against a name. Sleeper uses the team abbreviation as the
defense's player_id, which makes the team code the canonical id for free.
"""

from draftkit.identity.normalize import normalize_name

# abbreviation -> (city, nickname)
TEAMS: dict[str, tuple[str, str]] = {
    "ARI": ("Arizona", "Cardinals"),
    "ATL": ("Atlanta", "Falcons"),
    "BAL": ("Baltimore", "Ravens"),
    "BUF": ("Buffalo", "Bills"),
    "CAR": ("Carolina", "Panthers"),
    "CHI": ("Chicago", "Bears"),
    "CIN": ("Cincinnati", "Bengals"),
    "CLE": ("Cleveland", "Browns"),
    "DAL": ("Dallas", "Cowboys"),
    "DEN": ("Denver", "Broncos"),
    "DET": ("Detroit", "Lions"),
    "GB": ("Green Bay", "Packers"),
    "HOU": ("Houston", "Texans"),
    "IND": ("Indianapolis", "Colts"),
    "JAX": ("Jacksonville", "Jaguars"),
    "KC": ("Kansas City", "Chiefs"),
    "LAC": ("Los Angeles", "Chargers"),
    "LAR": ("Los Angeles", "Rams"),
    "LV": ("Las Vegas", "Raiders"),
    "MIA": ("Miami", "Dolphins"),
    "MIN": ("Minnesota", "Vikings"),
    "NE": ("New England", "Patriots"),
    "NO": ("New Orleans", "Saints"),
    "NYG": ("New York", "Giants"),
    "NYJ": ("New York", "Jets"),
    "PHI": ("Philadelphia", "Eagles"),
    "PIT": ("Pittsburgh", "Steelers"),
    "SEA": ("Seattle", "Seahawks"),
    "SF": ("San Francisco", "49ers"),
    "TB": ("Tampa Bay", "Buccaneers"),
    "TEN": ("Tennessee", "Titans"),
    "WAS": ("Washington", "Commanders"),
}

# Every other spelling of a team code we have actually seen in a feed, plus the
# relocations that still appear in older data.
ALIASES: dict[str, str] = {
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "GBP": "GB",
    "HST": "HOU",
    "JAC": "JAX",
    "KCC": "KC",
    "LVR": "LV",
    "NEP": "NE",
    "NOS": "NO",
    "SFO": "SF",
    "TBB": "TB",
    "WFT": "WAS",
    "WSH": "WAS",
    "OAK": "LV",  # relocated
    "SD": "LAC",
    "SDG": "LAC",
    "STL": "LAR",
    "LA": "LAR",
}


def canonical_team(code: str | None) -> str | None:
    """Fold any spelling of a team code onto the one Sleeper uses."""
    if not code:
        return None
    upper = code.strip().upper()
    if upper in TEAMS:
        return upper
    return ALIASES.get(upper)


def _defense_index() -> dict[str, str]:
    """Every phrase that identifies a team, mapped to its abbreviation."""
    index: dict[str, str] = {}
    for abbr, (city, nickname) in TEAMS.items():
        for phrase in (f"{city} {nickname}", city, nickname, abbr):
            index[normalize_name(phrase)] = abbr
    for alias, abbr in ALIASES.items():
        index[normalize_name(alias)] = abbr
    return index


_DEFENSE_INDEX = _defense_index()

# Words sources tack onto a defense's name that carry no identity.
_NOISE = ("defense", "dst", "d st", "def", "special teams")


def team_from_defense_name(name: str) -> str | None:
    """Work out which team a defense belongs to, however it is written.

    Handles "San Francisco 49ers", "San Francisco Defense", "49ers D/ST",
    "SF DST" and the rest, because every source names them differently and none
    of them provides an id we can join on.
    """
    normalized = normalize_name(name)
    for noise in _NOISE:
        normalized = normalized.replace(noise, " ")
    normalized = " ".join(normalized.split())
    if not normalized:
        return None
    if normalized in _DEFENSE_INDEX:
        return _DEFENSE_INDEX[normalized]
    # Fall back to the longest phrase that appears in the name, so "San
    # Francisco 49ers" is not matched by a stray "san".
    best: tuple[int, str] | None = None
    for phrase, abbr in _DEFENSE_INDEX.items():
        if len(phrase) < 4:
            continue
        if phrase in normalized and (best is None or len(phrase) > best[0]):
            best = (len(phrase), abbr)
    return best[1] if best else None
