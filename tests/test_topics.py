import pytest

from newsent.topics import TOPICS, topics_of


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Inflation cools as central bank holds rates", ("economy",)),
        ("Ethiopia-Eritrea border clashes raise fears of war", ("conflict",)),
        ("Serbia's MPs take seats in parliament after election", ("politics",)),
        ("Storm Charles causes floods across southern Europe", ("climate",)),
        ("Nvidia warns chip buyers of legal risks", ("tech",)),
        ("Cricket team wins the final", ()),
    ],
)
def test_tags_each_topic_from_its_keywords(title, expected):
    assert topics_of(title) == expected


def test_returns_every_matching_topic_in_registry_order():
    title = "AI data centres put out more carbon emissions, and tariffs bite"
    assert topics_of(title) == ("economy", "climate", "tech")


def test_ignores_case_for_plain_words():
    assert topics_of("CLIMATE TALKS STALL AT COP31") == ("climate",)
    assert topics_of("Ukraine Attacks Kerch Bridge") == ("conflict",)


def test_matches_word_endings_only_where_the_keyword_allows_them():
    assert topics_of("New tariffs hit exporters") == ("economy",)
    assert topics_of("Warm weather lifts Warner Bros box office") == ()
    assert topics_of("Lifetime award for war reporter") == ("conflict",)


@pytest.mark.parametrize(
    "title",
    [
        "Minister said the Thai talks went well",
        "Ai Weiwei opens new exhibition",
        "Princess Aiko arrives in Singapore",
        "AIDS funding cut in half",
    ],
)
def test_ai_does_not_match_inside_words_or_in_other_cases(title):
    assert "tech" not in topics_of(title)


@pytest.mark.parametrize(
    "title",
    [
        "Google bets on AI",
        "AI-powered tutors arrive in schools",
        "How A.I. Is Changing Hollywood",
        "Investors cool on AI's promise",
    ],
)
def test_ai_matches_the_acronym(title):
    assert "tech" in topics_of(title)


def test_fed_matches_the_central_bank_not_fed_up():
    assert topics_of("Fed's Musalem says more hikes may be needed") == ("economy",)
    assert topics_of("Commuters fed up with delays") == ()


def test_west_bank_is_not_economy():
    assert "economy" not in topics_of("Settlers attack village in West Bank")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Drone strike kills five", ("conflict",)),
        ("Airstrikes on Iran missile sites", ("conflict",)),
        ("France hit by nationwide public sector strike", ("economy",)),
        ("Teachers go on strike over pay", ("economy",)),
        ("Bridge damaged in major strike", ()),
        ("Former England striker writes memoir", ()),
    ],
)
def test_strike_is_tagged_only_when_qualified(title, expected):
    assert topics_of(title) == expected


def test_spaces_in_keywords_also_match_hyphens():
    assert topics_of("Giga Energy builds a data-centre in Texas") == ("tech",)
    assert topics_of("Leaders agree a cease-fire") == ("conflict",)


def test_every_keyword_tags_its_own_topic():
    for topic in TOPICS:
        for keyword in topic.keywords:
            title = f"Report: {keyword.removesuffix('*')} today"
            assert topic.key in topics_of(title), keyword


def test_topic_keys_are_unique():
    keys = [topic.key for topic in TOPICS]
    assert len(keys) == len(set(keys))
