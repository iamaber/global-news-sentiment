from newsent.stories import group_stories

CRIMEA = [
    ("Ukraine strikes Crimea bridge in 'unprecedented' attack", "europe"),
    ("\u2018Unprecedented\u2019 Ukraine attack on Crimean bridge", "mea"),
    (
        "Ukraine strikes major Russian bridge in Crimea with drones and missiles",
        "europe",
    ),
    (
        "Ukraine strikes major Russian bridge with drones and missiles as aerial "
        "attacks escalate",
        "americas",
    ),
]
SANCTIONS = [
    ("UK sanctions firms over Israeli West Bank settlements", "europe"),
    ("UK sanctions eight Israeli construction firms over West Bank settlements", "mea"),
]


def titles(story, headlines):
    return {headlines[i][0] for i in story.members}


def test_groups_one_event_reported_by_several_regions():
    headlines = [*CRIMEA, ("Pope Leo wraps up South America tour", "americas")]

    [story] = group_stories(headlines)

    assert titles(story, headlines) == {title for title, _ in CRIMEA}
    assert story.regions == {"europe", "mea", "americas"}
    assert story.lead in story.members


def test_matches_titles_despite_case_punctuation_and_plurals():
    headlines = [
        ("Ukraine strikes Crimea bridge", "europe"),
        ("UKRAINE STRIKE ON CRIMEA BRIDGES!", "asia_pacific"),
    ]

    assert len(group_stories(headlines)) == 1


def test_does_not_merge_a_different_event_that_shares_some_words():
    kyiv = ("Ukraine: Two bridges in Kyiv heavily damaged by Russian strikes", "mea")
    headlines = [*CRIMEA, kyiv]

    [story] = group_stories(headlines)

    assert kyiv[0] not in titles(story, headlines)


def test_drops_stories_covered_by_one_region_only():
    headlines = [(title, "europe") for title, _ in SANCTIONS]

    assert group_stories(headlines) == []


def test_unrelated_headlines_form_no_story():
    headlines = [
        ("Trump arrives in Philippines to kick off Asia trip", "americas"),
        ("Trump warns Iran over reported dirty bomb threat", "mea"),
    ]

    assert group_stories(headlines) == []
    assert group_stories([]) == []


def test_links_headlines_through_a_shared_neighbour():
    headlines = [
        ("Iran dismisses report of alleged dirty bomb attack on Washington", "europe"),
        ("Is Iran plotting a dirty bomb attack in the US? What we know", "mea"),
        (
            "Iran fires drones at U.S. base in Bahrain, denies reports of planned "
            "dirty bomb attack in D.C.",
            "americas",
        ),
    ]

    [story] = group_stories(headlines)

    assert len(story.members) == 3


def test_orders_by_region_count_then_size():
    melbourne = [
        ("Body of Melbourne Cup horse found dumped in Sydney skip", "europe"),
        ("Melbourne Cup runner So You Are found in Sydney skip bin", "asia_pacific"),
    ]
    headlines = [*melbourne, *SANCTIONS, *SANCTIONS[:1], *CRIMEA]

    stories = group_stories(headlines)

    assert [len(s.regions) for s in stories] == [3, 2, 2]
    assert [len(s.members) for s in stories] == [4, 3, 2]
    assert titles(stories[2], headlines) == {title for title, _ in melbourne}
