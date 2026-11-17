import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

SIMILARITY_THRESHOLD = 0.35

STOPWORDS = frozenset(
    """
    a an the and or but if of to in on at by for with from into onto over under
    about after before as is are was were be been being has have had do does did
    will would can could may might must shall should it its this that these those
    he she they them his her their we our you your i me my us not no nor so than
    then there here who whom whose which what when where why how new says said say
    amid up down out off more most less least very just also
    """.split()
)
WORD = re.compile(r"\w+")
APOSTROPHES = str.maketrans("", "", "'\u2019")


@dataclass(frozen=True, slots=True)
class Story:
    members: tuple[int, ...]
    regions: frozenset[str]
    lead: int


def title_tokens(title: str) -> frozenset[str]:
    words = WORD.findall(title.casefold().translate(APOSTROPHES))
    return frozenset(
        _singular(word) for word in words if len(word) > 1 and word not in STOPWORDS
    )


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def group_stories(headlines: Sequence[tuple[str, str]]) -> list[Story]:
    tokens = [title_tokens(title) for title, _ in headlines]
    parent = list(range(len(headlines)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in combinations(range(len(headlines)), 2):
        if similarity(tokens[i], tokens[j]) >= SIMILARITY_THRESHOLD:
            parent[root(i)] = root(j)

    groups: dict[int, list[int]] = {}
    for i in range(len(headlines)):
        groups.setdefault(root(i), []).append(i)

    stories = []
    for members in groups.values():
        regions = frozenset(headlines[i][1] for i in members)
        if len(regions) < 2:
            continue
        lead = max(
            members,
            key=lambda i: sum(similarity(tokens[i], tokens[j]) for j in members),
        )
        stories.append(Story(tuple(members), regions, lead))
    stories.sort(key=lambda s: (-len(s.regions), -len(s.members), s.members[0]))
    return stories
