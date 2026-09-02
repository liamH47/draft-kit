"""What a pasted cheat sheet actually looks like when it lands.

Every sample here is a shape a real paste produces: a PDF selected whole, a
spreadsheet column, a CSV export, a table dragged off a page. The parser is
judged on two things — it must not lose players, and it must not invent them.
"""

from draftkit.identity.ranklist import parse_ranking_text


def test_a_numbered_list_keeps_its_own_numbers():
    rows = parse_ranking_text("1. Ja'Marr Chase WR CIN\n2. Bijan Robinson RB ATL")
    assert [(r.rank, r.name, r.position, r.team) for r in rows] == [
        (1, "Ja'Marr Chase", "WR", "CIN"),
        (2, "Bijan Robinson", "RB", "ATL"),
    ]


def test_an_unnumbered_list_is_ranked_by_its_order():
    rows = parse_ranking_text("Ja'Marr Chase\nBijan Robinson\nJustin Jefferson")
    assert [r.rank for r in rows] == [1, 2, 3]
    assert rows[2].name == "Justin Jefferson"


def test_numbers_are_ignored_unless_every_row_has_one_and_they_climb():
    """A PDF pasted whole drops its page numbers into the middle of the list.
    Honouring a partial numbering would renumber half the board."""
    rows = parse_ranking_text("1. Ja'Marr Chase WR\nBijan Robinson RB\n3. Justin Jefferson WR")
    assert [r.rank for r in rows] == [1, 2, 3]
    assert [r.name for r in rows] == ["Ja'Marr Chase", "Bijan Robinson", "Justin Jefferson"]


def test_numbers_that_go_backwards_are_not_trusted():
    rows = parse_ranking_text("5. Ja'Marr Chase WR\n2. Bijan Robinson RB")
    assert [r.rank for r in rows] == [1, 2]


def test_separators_a_paste_actually_uses():
    for text in (
        "1,Justin Jefferson,WR,MIN",
        "1\tJustin Jefferson\tWR\tMIN",
        "1 | Justin Jefferson | WR | MIN",
        "1   Justin Jefferson   WR   MIN",
        "1. Justin Jefferson WR MIN",
    ):
        (row,) = parse_ranking_text(text)
        assert (row.name, row.position, row.team) == ("Justin Jefferson", "WR", "MIN"), text


def test_a_positional_rank_names_the_position_for_free():
    (row,) = parse_ranking_text("RB4 Saquon Barkley PHI")
    assert (row.name, row.position, row.team) == ("Saquon Barkley", "RB", "PHI")


def test_publisher_spellings_of_a_position_all_land_on_ours():
    for written, expected in (("DST", "DEF"), ("D/ST", "DEF"), ("PK", "K"), ("Defense", "DEF")):
        (row,) = parse_ranking_text(f"1. Somebody Else {written}")
        assert row.position == expected, written


def test_bye_furniture_is_stripped_out_of_the_name():
    for text in (
        "1. Ja'Marr Chase WR CIN (BYE 10)",
        "1. Ja'Marr Chase WR CIN (10)",
        "1. Ja'Marr Chase WR CIN bye: 10",
    ):
        (row,) = parse_ranking_text(text)
        assert row.name == "Ja'Marr Chase", text


def test_page_furniture_never_becomes_a_player():
    """The title, the header row and the page number all survive column
    splitting, and every one of them would otherwise be stored and then fail
    to resolve — burying the real misses the user needs to see."""
    rows = parse_ranking_text(
        "2026 Draft Cheat Sheet\n"
        "Rank  Player  Pos  Team  Bye\n"
        "1.  Ja'Marr Chase  WR  CIN\n"
        "\n"
        "   \n"
        "-----\n"
        "Page 2 of 7\n"
        "2.  Bijan Robinson  RB  ATL\n"
    )
    assert [r.name for r in rows] == ["Ja'Marr Chase", "Bijan Robinson"]


def test_a_team_defense_survives_the_digits_rule():
    """Digits mean furniture — except the 49ers, who are a real team."""
    rows = parse_ranking_text("1. San Francisco 49ers DST\n2. Page 4")
    assert [r.name for r in rows] == ["San Francisco 49ers"]


def test_nothing_in_nothing_out():
    assert parse_ranking_text("") == []
    assert parse_ranking_text("\n\n   \n") == []
    assert parse_ranking_text("12\n---\n7") == []


def test_a_row_whose_name_column_came_through_empty_is_dropped():
    """Every way a paste can carry a rank and no player: the name column blank,
    the whole row blank behind a positional rank, a dash where a name should
    be. None of them may become a player called "-"."""
    assert parse_ranking_text("1,,WR,CIN\n2,,RB,ATL") == []
    assert parse_ranking_text("RB1,,,") == []
    assert parse_ranking_text("1. - WR CIN") == []


def test_a_name_with_no_position_or_team_still_counts():
    (row,) = parse_ranking_text("Malik Nabers")
    assert (row.rank, row.name, row.position, row.team) == (1, "Malik Nabers", None, None)


def test_a_position_column_that_is_only_a_position_is_not_read_as_a_name():
    rows = parse_ranking_text("1. Travis Kelce TE KC\n2. Trey McBride TE ARI")
    assert [(r.name, r.position, r.team) for r in rows] == [
        ("Travis Kelce", "TE", "KC"),
        ("Trey McBride", "TE", "ARI"),
    ]


def test_a_suffix_does_not_derail_the_name():
    """The trailing dot goes with the rank-marker punctuation, which is fine:
    the resolver normalizes suffixes away, so both spellings are one player."""
    from draftkit.identity.normalize import normalize_name

    (row,) = parse_ranking_text("1. Marvin Harrison Jr. WR ARI")
    assert row.name.startswith("Marvin Harrison Jr")
    assert normalize_name(row.name) == normalize_name("Marvin Harrison Jr.")
    assert (row.position, row.team) == ("WR", "ARI")


def test_the_position_is_taken_from_a_cell_before_the_name_tail():
    """When both a column and a run-on tail name a position, the column wins
    and the tail is not double-consumed."""
    (row,) = parse_ranking_text("1,Justin Jefferson WR,WR,MIN")
    assert (row.name, row.position, row.team) == ("Justin Jefferson", "WR", "MIN")


def test_a_team_in_brackets_is_metadata_not_part_of_the_name():
    """ "Jahmyr Gibbs (DET)" is how most on-page draft boards render a row, and
    it is the shape that fails worst: glued onto the name it loses the team AND
    the player, so every single row of such a list comes back unmatched."""
    for text in (
        "1  Jahmyr Gibbs (DET)  RB1",
        "1\tJahmyr Gibbs (DET)\tRB1",
        "1 Jahmyr Gibbs (DET) RB1",
        "1 | Jahmyr Gibbs | (DET) | RB1",
        "1  Jahmyr Gibbs [DET]  RB1",
    ):
        (row,) = parse_ranking_text(text)
        assert (row.name, row.position, row.team) == ("Jahmyr Gibbs", "RB", "DET"), text


def test_a_bracketed_board_carries_its_bye_column_and_its_defenses():
    """The same boards put a bye week in the last column and spell a defense
    out in full. Neither may cost the row."""
    rows = parse_ranking_text(
        "170\tJerry Jeudy (CLE)\tWR63\t11\n171\tPhiladelphia Eagles (PHI)\tDST5\t10"
    )
    assert [(r.rank, r.name, r.position, r.team) for r in rows] == [
        (170, "Jerry Jeudy", "WR", "CLE"),
        (171, "Philadelphia Eagles", "DEF", "PHI"),
    ]
