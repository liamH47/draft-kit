import pytest

from draftkit.identity.normalize import normalize_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("A.J. Brown", "aj brown"),
        ("AJ Brown", "aj brown"),
        ("Ja'Marr Chase", "jamarr chase"),
        ("Ja’Marr Chase", "jamarr chase"),  # noqa: RUF001 — curly apostrophe from real feeds
        ("Kenneth Walker III", "kenneth walker"),
        ("Marvin Harrison Jr.", "marvin harrison"),
        ("Jaxon Smith-Njigba", "jaxon smith njigba"),
        ("Amon-Ra St. Brown", "amon ra st brown"),
        ("  Puka   Nacua ", "puka nacua"),
        ("Eddy Piñeiro", "eddy pineiro"),  # FFC keeps the ñ, Sleeper drops it
        ("Dónta Foreman", "donta foreman"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_name(raw) == expected


def test_variants_collide():
    assert normalize_name("A.J. Brown") == normalize_name("AJ Brown Jr")
