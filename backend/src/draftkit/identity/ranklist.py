"""Turn a pasted ranking list into rows we can join on.

The input is whatever came off somebody's clipboard: a PDF cheat sheet, a
column copied out of a spreadsheet, a table scraped off a page by selecting
it. All of those arrive as ragged text with page furniture mixed in, so this
module is deliberately forgiving about shape and deliberately strict about
what it will call a player.

Shapes it handles:

    1. Ja'Marr Chase WR CIN
    2  Bijan Robinson  RB  ATL
    3,Justin Jefferson,WR,MIN
    RB4 Saquon Barkley PHI (BYE 9)
    Malik Nabers

What it throws away: blank lines, page numbers, and repeated header rows,
because a PDF pasted whole carries one of each per page and every one of them
would otherwise become a player named "Rank".

Pure text in, structured rows out: no I/O, no network, no database. Resolving
a name to a player id is a separate step, done by the Resolver, so a list can
be parsed and counted before anything is stored.
"""

import re
from dataclasses import dataclass
from itertools import pairwise

from draftkit.identity.teams import canonical_team, team_from_defense_name

# Sleeper's positions plus the spellings other publishers use for them.
_POSITIONS = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "K": "K",
    "PK": "K",
    "DEF": "DEF",
    "DST": "DEF",
    "D/ST": "DEF",
    "DEFENSE": "DEF",
}

# Words that only ever appear in a table header or page furniture. A line whose
# name would be one of these is chrome, not a player.
_FURNITURE = {
    "rank",
    "rk",
    "player",
    "players",
    "name",
    "pos",
    "position",
    "team",
    "tm",
    "bye",
    "tier",
    "adp",
    "notes",
    "page",
    "overall",
    "cheat sheet",
    "draft board",
}

# "1." / "12)" / "3 -" at the head of a line.
_LEADING_RANK = re.compile(r"^\s*(\d{1,3})\s*[.)\]:,;|-]\s*|^\s*(\d{1,3})\s+")
# "RB1" / "WR12" — a positional rank, which names the position for free.
_POS_RANK = re.compile(r"^\s*([A-Za-z/]{1,7})\s*(\d{1,3})\b\s*")
# "(BYE 9)", "(9)", "bye: 9" — trailing bye furniture nobody wants in a name.
_BYE = re.compile(r"\((?:bye[\s:]*)?\d{1,2}\)|\bbye[\s:]+\d{1,2}\b", re.IGNORECASE)
# A name has to have letters in it. "12", "-", "*" do not.
_HAS_LETTERS = re.compile(r"[A-Za-z]")
_HAS_DIGITS = re.compile(r"\d")


@dataclass(frozen=True)
class RankedName:
    """One line of a pasted list, before it is resolved to a player id."""

    rank: int
    name: str
    position: str | None = None
    team: str | None = None


def _cells(line: str) -> list[str]:
    """Split a line into cells on whatever separator it actually uses."""
    for sep in ("\t", "|", ","):
        if sep in line:
            return [c.strip() for c in line.split(sep) if c.strip()]
    # Aligned columns from a PDF come through as runs of spaces.
    if re.search(r"\s{2,}", line):
        return [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]
    return [line.strip()]


def _take_position(cells: list[str]) -> tuple[str | None, list[str]]:
    """Pull a standalone position cell out, if one of the cells is nothing but
    a position. A position buried inside a name cell is handled later."""
    for i, cell in enumerate(cells):
        stripped = re.sub(r"\d+$", "", cell.strip()).upper()
        if stripped in _POSITIONS:
            return _POSITIONS[stripped], cells[:i] + cells[i + 1 :]
    return None, cells


def _take_team(cells: list[str]) -> tuple[str | None, list[str]]:
    """Same for a cell that is nothing but a team code."""
    for i, cell in enumerate(cells):
        team = canonical_team(cell.strip())
        if team and len(cell.strip()) <= 4:
            return team, cells[:i] + cells[i + 1 :]
    return None, cells


def _split_trailing_tokens(name: str) -> tuple[str, str | None, str | None]:
    """Peel a position and a team off the end of a single run-on cell, which
    is what "Ja'Marr Chase WR CIN" arrives as when nothing was aligned."""
    position: str | None = None
    team: str | None = None
    tokens = name.split()
    # Work from the right: the tail is where the metadata lives.
    while len(tokens) > 1:
        tail = tokens[-1].strip(".,")
        bare = re.sub(r"\d+$", "", tail).upper()
        if team is None and canonical_team(tail):
            team = canonical_team(tail)
        elif position is None and bare in _POSITIONS:
            position = _POSITIONS[bare]
        else:
            break
        tokens = tokens[:-1]
    return " ".join(tokens), position, team


def _is_player_name(name: str) -> bool:
    """Reject what a pasted PDF leaves behind that is not a person.

    Page numbers, running titles and repeated header rows all survive the
    column splitting, and every one of them would otherwise be stored as a
    player and then fail to resolve — burying the handful of real misses the
    user actually needs to fix. Digits are the giveaway, since no footballer
    has one in his name; team defenses do ("49ers"), so they get asked.
    """
    if not name or not _HAS_LETTERS.search(name):
        return False
    if name.lower() in _FURNITURE:
        return False
    return not (_HAS_DIGITS.search(name) and not team_from_defense_name(name))


def _ranks_ascend(ranks: list[int | None]) -> bool:
    """True when every row carried its own number and those numbers climb.

    Anything less than unanimous means the paste mixed page furniture into the
    numbering, and the list's own order is the more trustworthy ranking.
    """
    numbers = [r for r in ranks if r is not None]
    if not numbers or len(numbers) != len(ranks):
        return False
    return all(a < b for a, b in pairwise(numbers))


def parse_ranking_text(text: str) -> list[RankedName]:
    """Parse a pasted list into ranked names, in the order they appear.

    Explicit numbers are honoured only when EVERY row carries one and they
    ascend: a PDF that pastes its page numbers into the middle of the list
    would otherwise renumber half the board. Anything less than unanimous and
    the list's own order is used, which is what a ranking list means anyway.
    """
    parsed: list[tuple[int | None, RankedName]] = []
    for raw_line in text.splitlines():
        line = _BYE.sub(" ", raw_line).strip()
        if not line or not _HAS_LETTERS.search(line):
            continue

        explicit: int | None = None
        position: str | None = None

        match = _LEADING_RANK.match(line)
        if match:
            explicit = int(match.group(1) or match.group(2))
            line = line[match.end() :]
        else:
            pos_match = _POS_RANK.match(line)
            if pos_match and pos_match.group(1).upper() in _POSITIONS:
                position = _POSITIONS[pos_match.group(1).upper()]
                explicit = int(pos_match.group(2))
                line = line[pos_match.end() :]

        cells = _cells(line)
        if not cells:
            continue
        cell_position, cells = _take_position(cells)
        team, cells = _take_team(cells)
        if not cells:
            continue

        name, tail_position, tail_team = _split_trailing_tokens(cells[0])
        position = position or cell_position or tail_position
        team = team or tail_team
        name = name.strip(" .,-")
        if not _is_player_name(name):
            continue
        parsed.append((explicit, RankedName(0, name, position, team)))

    honour = _ranks_ascend([r for r, _ in parsed])
    out = []
    for i, (explicit, row) in enumerate(parsed, start=1):
        rank = explicit if honour and explicit is not None else i
        out.append(RankedName(rank, row.name, row.position, row.team))
    return out
