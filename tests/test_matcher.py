from src.matcher import normalize


def test_normalize_is_case_and_whitespace_insensitive():
    assert normalize("  United   Kingdom ") == normalize("united kingdom")


KNOWN_DIRECT_MATCHES = {
    "Oman": "Oman",
    "United Arab Emirates": "United Arab Emirates",
    "Monaco": "Monaco",
    "Australia": "Australia",
}


def test_known_countries_match_directly(matcher):
    for raw_name, expected in KNOWN_DIRECT_MATCHES.items():
        result = matcher.match(raw_name)
        assert result.status == "matched", raw_name
        assert result.matched_value == expected


def test_iraq_composite_includes_iraqi_kurdistan(matcher):
    """Natural Earth splits Iraq into 'Iraq' and the autonomous 'Iraqi
    Kurdistan' region under one ADMIN value -- both must be highlighted,
    or the map shows a visibly incomplete/wrong-shaped Iraq."""
    result = matcher.match("Iraq")
    assert result.status == "matched"
    assert result.match_type == "composite"
    assert len(result.entity_ids) == 2


def test_alias_examples_from_spec_resolve(matcher):
    cases = {
        # UK is a composite of 4 home-nation polygons (no single UK
        # polygon exists in the dataset), so it's checked separately below.
        "USA": "United States of America",
        "UAE": "United Arab Emirates",
        "Ivory Coast": "Côte d'Ivoire",
        "Czech Republic": "Czechia",
        "Cape Verde": "Cabo Verde",
    }
    for raw_name, expected in cases.items():
        result = matcher.match(raw_name)
        assert result.status == "matched", raw_name
        assert result.matched_value == expected

    uk_result = matcher.match("UK")
    assert uk_result.status == "matched"
    assert uk_result.match_type == "alias"
    assert len(uk_result.entity_ids) == 4


def test_united_kingdom_composite_resolves_to_four_home_parts(matcher):
    result = matcher.match("United Kingdom")
    assert result.status == "matched"
    assert result.match_type == "composite"
    assert len(result.entity_ids) == 4


def test_nonsense_name_is_unmatched_not_guessed(matcher):
    result = matcher.match("Definitely Not A Real Country Xyzzy")
    assert result.status == "unmatched"
    assert result.entity_ids is None


def test_bare_virgin_islands_resolves_to_us_virgin_islands(matcher):
    """Natural Earth has no single 'Virgin Islands' -- only US and British
    Virgin Islands separately -- so this was left unresolved until
    reconciliation.csv independently confirmed the traveller's bare
    'Virgin Islands' entry was specifically the U.S. Virgin Islands (its
    own explicit 'U.S. Virgin Islands' row, with a note). That is now a
    real alias, not a guess."""
    result = matcher.match("Virgin Islands")
    assert result.status == "matched"
    assert result.matched_value == "U.S. Virgin Is."


def test_bare_virgin_islands_never_resolves_to_british(matcher):
    """The resolution must never silently substitute the wrong territory."""
    result = matcher.match("Virgin Islands")
    assert result.matched_value != "British Virgin Is."

    british = matcher.match("British Virgin Islands")
    assert british.status == "matched"
    assert british.matched_value == "British Virgin Is."
    assert british.entity_ids != result.entity_ids
