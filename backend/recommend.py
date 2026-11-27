"""Pure recommendation logic: seeds -> taste profiles -> scored, explained picks.

No I/O in here, so it is fast enough to re-score live while the vibe is tweaked.
"""
import math
import statistics
from datetime import date
from bisect import bisect_left, bisect_right
import re
from functools import lru_cache
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace

from .letterboxd import Film, UserData

# ---------------------------------------------------------------- vibe vocabulary

MOODS = {
    "cozy": {
        "label": "Cozy",
        "genres": {"Comedy": 0.6, "Family": 0.9, "Animation": 0.8, "Romance": 0.25},
        "kw": ["heartwarming", "feel-good", "charming", "wholesome", "cozy", "sweet", "touching", "friendship",
               "whimsical", "delightful", "uplifting", "endearing", "gentle", "comforting", "heartfelt"],
        "anti": ["horror", "gore", "violent", "disturbing", "brutal", "terrifying", "grisly", "heartbreak", "war", "nazi",
                 "holocaust", "suffering"],
    },
    "tense": {
        "label": "Thrilling",
        "genres": {"Thriller": 1.0, "Crime": 0.7, "Action": 0.6, "Mystery": 0.6},
        "kw": ["tense", "suspense", "gripping", "thrilling", "heist", "chase", "nerve", "survival",
               "conspiracy", "espionage", "spy", "cat-and-mouse", "pulse", "high-stakes", "adrenaline"],
        "anti": ["heartwarming", "whimsical", "wholesome"],
    },
    "funny": {
        "label": "Funny",
        "genres": {"Comedy": 1.0},
        "kw": ["funny", "hilarious", "comedy", "comedic", "witty", "quirky", "absurd", "satire", "humor",
               "humour", "laugh", "slapstick", "outrageous", "zany", "raunchy", "parody", "deadpan"],
        "anti": ["tragic", "heartbreak", "grief", "suffering", "bleak", "nazi", "holocaust"],
    },
    "emotional": {
        "label": "Emotional",
        "genres": {"Drama": 0.8, "Romance": 0.5},
        "kw": ["moving", "heartbreak", "tragic", "emotional", "tear", "grief", "loss", "sad", "poignant",
               "touching", "sentimental", "melancholy", "devastating", "suffering", "mourning"],
        "anti": ["slapstick", "zany", "raunchy"],
    },
    "mindbend": {
        "label": "Mind-bending",
        "genres": {"Science Fiction": 0.6, "Mystery": 0.5, "Thriller": 0.3},
        # Letterboxd tags real head-trips "surreal", "dreamlike", "thought-provoking"; its "twisted dark
        # psychological thriller" sits on every crime procedural, so "twist" counts but "psychological" doesn't
        "kw": ["mind-bending", "twist", "surreal", "dream", "thought-provoking", "reality", "time travel", "puzzle",
               "philosophical", "existential", "cerebral", "enigmatic", "paranoia", "identity", "memory",
               "simulation", "nonlinear", "unreliable"],
        "anti": ["slapstick", "wholesome"],
        # Letterboxd hangs "Surreal and thought-provoking visions of life and death" on every weighty drama and
        # on Princess Mononoke; nobody leaves those films asking what was real
        "ignore": ["visions of life and death"],
    },
    "dark": {
        "label": "Scary",
        "genres": {"Horror": 1.0, "Thriller": 0.5},
        "kw": ["horror", "terrifying", "creepy", "disturbing", "eerie", "haunting", "dread", "supernatural",
               "gore", "nightmare", "sinister", "bleak", "unsettling", "macabre", "chilling", "scary", "demonic",
               "slasher", "grisly"],
        "anti": ["heartwarming", "wholesome", "feel-good", "whimsical"],
    },
    "epic": {
        "label": "Epic adventure",
        "genres": {"Adventure": 1.0, "Fantasy": 0.8, "Science Fiction": 0.6, "War": 0.5, "Action": 0.5,
                   "History": 0.4},
        "kw": ["epic", "adventure", "quest", "journey", "spectacular", "battle", "kingdom", "galaxy", "legend",
               "heroic", "sweeping", "grand", "space", "mythical", "monster", "superhero", "empire"],
        "anti": ["nazi", "holocaust", "heartbreak"],
    },
    "romantic": {
        "label": "Romantic",
        "genres": {"Romance": 1.0},
        "kw": ["romance", "romantic", "love", "passion", "lovers", "falling in love", "desire", "courtship"],
        "anti": ["gore", "slasher", "terrifying"],
    },
    "artful": {
        "label": "Artsy",
        "genres": {"Drama": 0.4, "Fantasy": 0.3},
        "kw": ["beautiful", "poetic", "dreamlike", "atmospheric", "visually", "stunning", "contemplative",
               "meditative", "lyrical", "artistic", "beauty", "mesmerizing", "surreal", "quiet", "ethereal",
               "elegant"],
        "anti": ["slapstick", "raunchy", "superhero"],
    },
    "true": {
        "label": "True story",
        "genres": {"Documentary": 1.0, "History": 0.6},
        "kw": ["true story", "documentary", "biography", "biopic", "real-life", "historical", "based on",
               "inspiring", "politics", "journalism", "musician", "legacy"],
        "anti": ["supernatural", "superhero", "fantasy"],
    },
}

# Genres that make a film read as the *wrong* mood to a person, however many keywords it hits
# (Isle of Dogs is tagged Adventure, but nobody calls a 100-minute stop-motion comedy an "epic escape").
AVOID = {
    "cozy": {"Horror": 1.0, "War": 0.8, "Thriller": 0.6, "Crime": 0.5},
    "tense": {"Family": 1.0, "Documentary": 0.8, "Animation": 0.6, "Romance": 0.3},
    "funny": {"War": 0.8, "Horror": 0.6, "Documentary": 0.5, "Thriller": 0.4},
    "emotional": {"Horror": 0.6, "Action": 0.4, "Crime": 0.4},
    "mindbend": {"Family": 0.8, "Documentary": 0.8, "Crime": 0.5, "Romance": 0.4, "Comedy": 0.3, "Horror": 0.3},
    "dark": {"Family": 1.0, "Comedy": 0.5, "Romance": 0.5, "Animation": 0.4},
    "epic": {"Documentary": 1.0, "Comedy": 0.6, "Horror": 0.5, "Crime": 0.4, "Romance": 0.3, "Family": 0.3, "Animation": 0.3},
    "romantic": {"Horror": 1.0, "War": 0.6, "Action": 0.3},
    "artful": {"Action": 0.6, "Family": 0.5, "Comedy": 0.3},
    "true": {"Fantasy": 1.0, "Science Fiction": 1.0, "Animation": 0.6, "Horror": 0.6},
}
# Moods a film can't really be without one of these genres (a romance needs Romance, a comedy needs Comedy)
CORE = {"funny": {"Comedy"}, "romantic": {"Romance"}, "dark": {"Horror", "Thriller"},
        "true": {"Documentary", "History"}, "tense": {"Thriller", "Crime", "Mystery", "Action"}}
# +1: the mood wants a long, sweeping film; -1: it wants a light, short one
LENGTH = {"epic": 1, "cozy": -1, "funny": -1}

ERAS = {"new": (2015, 9999), "modern": (1990, 2014), "classic": (0, 1989)}
ERA_DECADES = {"new": ["2010s", "2020s"], "modern": ["1990s", "2000s"], "classic": ["1960s", "1970s", "1980s"]}
# Letterboxd genre slugs to browse when a mood is picked (so the vibe can surface films outside everyone's taste)
MOOD_BROWSE = {"cozy": ["family", "animation"], "tense": ["thriller"], "funny": ["comedy"], "emotional": ["drama"],
               "mindbend": ["science-fiction", "mystery"], "dark": ["horror"], "epic": ["adventure", "fantasy"],
               "romantic": ["romance"], "artful": [], "true": ["documentary", "history"]}

DEFAULT_ANSWERS = {
    "moods": [],          # up to 2 MOODS keys; empty = anything
    "runtime": None,      # max minutes or None
    "era": "any",         # ERAS key or "any"
    "fame": "any",        # "popular" | "between" | "gem" | "any"
    "source": "mix",      # "watchlist" | "mix" | "discover"
    "subtitles": True,    # False = English-language only
    "animation": True,    # False = drop animated films
}

FEATURE_WEIGHTS = {"genre": 1.0, "theme": 0.9, "director": 1.6, "cast": 0.5, "country": 0.35, "lang": 0.35,
                   "decade": 0.35}


def features(f: Film) -> dict[str, float]:
    out = {}
    for g in f.genres:
        out[f"genre:{g}"] = FEATURE_WEIGHTS["genre"]
    for t in f.themes:
        out[f"theme:{t}"] = FEATURE_WEIGHTS["theme"]
    for d in f.directors:
        out[f"director:{d}"] = FEATURE_WEIGHTS["director"]
    for c in f.cast[:5]:
        out[f"cast:{c}"] = FEATURE_WEIGHTS["cast"]
    for c in f.countries[:2]:
        out[f"country:{c}"] = FEATURE_WEIGHTS["country"]
    if f.language:
        out[f"lang:{f.language}"] = FEATURE_WEIGHTS["lang"]
    if f.year:
        out[f"decade:{f.year // 10 * 10}"] = FEATURE_WEIGHTS["decade"]
    return out


# ---------------------------------------------------------------- seeds


@dataclass
class Seed:
    slug: str
    weight: float  # negative = disliked
    rating: int | None


def rating_scale(u: UserData) -> tuple[float, float]:
    """A user's own mean and spread: 3.5★ is a rave from a harsh rater and a shrug from a generous one."""
    rs = [f.rating for f in u.watched if f.rating]
    if len(rs) < 20:
        return 6.0, 2.0
    return statistics.mean(rs), max(statistics.pstdev(rs), 1.0)


def pick_seeds(u: UserData, n_pos: int = 40, n_neg: int = 20) -> list[Seed]:
    """The films that best describe a user's taste, judged against their own rating habits, recent first.
    Letterboxd likes are ignored on purpose."""
    total = max(len(u.watched), 1)
    mean, sd = rating_scale(u)
    scored, neg = [], []
    for i, f in enumerate(u.watched):
        recency = 1 - i / total
        r = f.rating
        if r is None:
            continue
        z = (r - mean) / sd
        if z <= -1.0 or r <= 3:
            neg.append(Seed(f.slug, -_clamp(0.3 * -z, 0.3, 0.9), r))
        elif z >= 0.6 and r >= 6:
            scored.append((z + recency, Seed(f.slug, _clamp(0.5 + 0.25 * z, 0.5, 1.2), r)))
    scored.sort(key=lambda x: -x[0])
    pos = [s for _, s in scored[:n_pos]]
    if len(pos) < 15:  # sparse profile: lean on what they watched recently, unless they rated it below par
        have = {s.slug for s in pos} | {s.slug for s in neg}
        pos += [Seed(f.slug, 0.4, f.rating) for f in u.watched
                if f.slug not in have and (f.rating is None or f.rating >= mean)][: 25 - len(pos)]
    return pos + neg[:n_neg]


def is_series(f: Film) -> bool:
    """Miniseries: Letterboxd lists them as films but TMDB has no movie id."""
    return bool(f.runtime and (f.runtime > 240 or (f.tmdb_id is None and f.runtime > 150)))


def discovery_seeds(seeds: dict[str, list[Seed]], films: dict[str, Film], per_user: int = 16) -> list[tuple[str, str]]:
    """(user, seed) pairs to follow into 'similar films'. Favourites several members share go first, credited to
    each of them, so a group's new finds grow out of common ground instead of one person's corner."""
    ok = {u: [s.slug for s in ss if s.weight > 0 and s.slug in films and not is_series(films[s.slug])]
          for u, ss in seeds.items()}
    lovers = defaultdict(list)
    for u, slugs in ok.items():
        for s in slugs:
            lovers[s].append(u)
    shared = [s for s in lovers if len(lovers[s]) > 1][:24] if len(seeds) > 1 else []
    pairs = [(u, s) for s in shared for u in lovers[s]]
    for u, slugs in ok.items():
        pairs += [(u, s) for s in slugs if s not in shared][:per_user]
    return pairs


# ---------------------------------------------------------------- pool


@dataclass
class Pool:
    """Everything gathered for a group, independent of the vibe answers."""
    users: list[UserData]
    films: dict[str, Film]
    seeds: dict[str, list[Seed]]                        # username -> seeds
    watchlisted: dict[str, set[str]]                    # slug -> usernames
    discovered: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # slug -> [(username, seed slug)]
    watched_any: set[str] = field(default_factory=set)
    vibe_found: dict[str, set[str]] = field(default_factory=dict)  # mood -> slugs from genre browsing


def watchlist_candidates(users: list[UserData], cap: int = 400) -> tuple[dict[str, set[str]], list[str]]:
    """slug -> who watchlisted it, plus a capped fetch order (shared first, then round-robin)."""
    watched = {f.slug for u in users for f in u.watched}
    who = defaultdict(set)
    for u in users:
        for s in u.watchlist:
            if s not in watched:
                who[s].add(u.profile.username)
    order, seen = [], set()
    for s in sorted((s for s in who if len(who[s]) > 1), key=lambda s: -len(who[s])):
        order.append(s)
        seen.add(s)
    queues = [[s for s in u.watchlist if s in who and s not in seen] for u in users]
    i = 0
    while any(queues) and len(order) < cap:
        q = queues[i % len(queues)]
        if q:
            s = q.pop(0)
            if s not in seen:
                seen.add(s)
                order.append(s)
        i += 1
    return dict(who), order[:cap]


def discovery_candidates(similar: dict[tuple[str, str], list[str]], watched: set[str], cap: int = 300):
    """similar[(username, seed)] -> slugs. Rank by how many seeds (and people) point at a film."""
    hits = defaultdict(list)
    for (user, seed), slugs in similar.items():
        for rank, s in enumerate(slugs):
            if s not in watched:
                hits[s].append((user, seed, rank))

    def strength(s):
        h = hits[s]
        return len({u for u, _, _ in h}) * 3 + sum(1 / (1 + r / 6) for _, _, r in h)

    ranked = sorted(hits, key=lambda s: -strength(s))[:cap]
    return {s: [(u, seed) for u, seed, _ in hits[s]] for s in ranked}


# ---------------------------------------------------------------- scoring


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _text(f: Film) -> tuple[str, str]:
    return " | ".join(f.themes + f.genres).lower(), f"{f.tagline} {f.synopsis}".lower()


@lru_cache(maxsize=None)
def _rx(words: tuple[str, ...]) -> re.Pattern:
    # word-start boundary so "tense" doesn't fire on "intense"; prefix ok so "romance" hits "romances"
    return re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + ")")


def _count(words, text: str) -> int:
    return len(set(_rx(tuple(words)).findall(text))) if words else 0


def mood_score(f: Film, mood: str) -> tuple[float, str | None]:
    """0..1 fit for one mood, plus the theme that best shows it (for the 'why')."""
    m = MOODS[mood]
    if m.get("ignore"):
        f = replace(f, themes=[t for t in f.themes if not any(x in t.lower() for x in m["ignore"])])
    themes, syn = _text(f)
    genre = max((m["genres"].get(g, 0) for g in f.genres), default=0)
    # themes are Letterboxd's curated nanogenres; a synopsis saying "epic journey" is cheap talk
    kw = _clamp((_count(m["kw"], themes) + 0.25 * _count(m["kw"], syn)) / 2)
    anti = _count(m["anti"], themes) * 0.3
    avoid = max((AVOID[mood].get(g, 0) for g in f.genres), default=0)
    shape = 0.5
    if LENGTH.get(mood) and f.runtime:
        long = _clamp((f.runtime - 105) / 45)  # 1h45 -> 0, 2h30 -> 1
        shape = long if LENGTH[mood] > 0 else 1 - long
    hits = [(_count(m["kw"], t.lower()) - _count(m["anti"], t.lower()), -i, t) for i, t in enumerate(f.themes)]
    best = max(hits, default=(0, 0, None))
    score = 0.45 * genre + 0.45 * kw + 0.2 * (shape - 0.5) - 0.45 * avoid - anti
    if mood in CORE and not CORE[mood] & set(f.genres):
        score = min(score, 0.15)
    return _clamp(score), best[2] if best[0] > 0 else None


def popularity(f: Film) -> float:
    """0..1 how well-known a film is in absolute terms. Counts ratings per year too, so a brand-new Brad Pitt
    film with 250k ratings reads as big, not as a deep cut next to classics with a million."""
    total = _clamp((math.log10(f.rating_count + 1) - 4.3) / 1.7)  # 20k -> 0, 1M -> 1
    age = max(1, date.today().year - (f.year or date.today().year))
    per_year = _clamp((math.log10(f.rating_count / age + 1) - 3.7) / 1.6)  # 5k/yr -> 0, 200k/yr -> 1
    return max(total, per_year)


def fame_fit(p: float, fame: str) -> float:
    """p = how well-known the film is (0..1), half absolute and half relative to tonight's candidates."""
    return {"popular": p, "gem": 1 - p, "between": 1 - abs(p - 0.5) * 2}.get(fame, 0.6)


def quality(f: Film) -> float:
    # saturates at 4.0: past that, "how good" matters less than "for us" (a 4.6 1963 classic isn't a better
    # Friday pick than a 4.0 film everyone's into)
    return _clamp((f.rating - 2.8) / 1.2) if f.rating else 0.35


def build_profiles(pool: Pool) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Per-user feature weights and an IDF table over every film we know.

    A profile is what someone loves *more than a typical film in tonight's pool has it*: most favourites are
    English-language dramas because most films are, so those cancel out and what's left is the real taste
    (Villeneuve, anime, war epics). Without this, any plain drama looked like everyone's cup of tea."""
    df = Counter()
    feats = {s: features(f) for s, f in pool.films.items()}
    for fv in feats.values():
        df.update(fv)  # sums weights, so df[k] / n is the pool's average value of feature k
    n = max(len(feats), 1)
    # plain log(n/df): "English" or "Drama" on half the films should say very little on its own
    idf = {k: math.log((n + 1) / (1 + c / FEATURE_WEIGHTS[k.split(":")[0]])) for k, c in df.items()}
    profiles = {}
    for user, seeds in pool.seeds.items():
        prof = defaultdict(float)
        net = 0.0
        for sd in seeds:
            if sd.slug in feats:
                net += sd.weight
                for k, w in feats[sd.slug].items():
                    prof[k] += sd.weight * w
        # people (directors, cast) are rare enough that their base rate is noise; only the broad strokes centre
        profiles[user] = {k: prof.get(k, 0.0) - (0 if k.startswith(("director:", "cast:")) else net * c / n)
                          for k, c in df.items()}
    return profiles, idf


def taste(fv: dict[str, float], prof: dict[str, float], idf: dict[str, float]) -> float:
    num = sum(prof.get(k, 0) * w * idf.get(k, 1) for k, w in fv.items())
    den = math.sqrt(sum((w * idf.get(k, 1)) ** 2 for k, w in fv.items())) or 1
    return num / den


def _rank01(values: dict[str, float]) -> dict[str, float]:
    """Percentile rank in [0, 1] (robust to wildly different profile scales)."""
    vals = sorted(values.values())
    n = max(len(vals) - 1, 1)
    # ties share their midpoint rank, so films nobody's taste says anything about all land in the middle
    return {s: (bisect_left(vals, v) + bisect_right(vals, v) - 1) / 2 / n for s, v in values.items()}


def _first_names(users: dict[str, UserData]) -> dict[str, str]:
    """'Knut Flom Eriksen' -> 'Knut', like friends say it; full names only if two share a first name."""
    first = {k: (u.profile.display_name or k).split()[0] for k, u in users.items()}
    clash = {n for n in first.values() if list(first.values()).count(n) > 1}
    return {k: users[k].profile.display_name if n in clash else n for k, n in first.items()}


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]


def recommend(pool: Pool, answers: dict | None = None, limit: int = 30) -> list[dict]:
    a = {**DEFAULT_ANSWERS, **(answers or {})}
    users = {u.profile.username: u for u in pool.users}
    display = _first_names(users)
    n_users = len(users)
    solo = n_users == 1

    if a["source"] == "watchlist":
        cand = set(pool.watchlisted)
    elif a["source"] == "discover":
        cand = set(pool.discovered) - set(pool.watchlisted)
    else:
        cand = set(pool.watchlisted) | set(pool.discovered)
    if a["source"] != "watchlist":
        for m in a["moods"]:
            cand |= pool.vibe_found.get(m, set()) - set(pool.watchlisted)
    cand = [s for s in cand - pool.watched_any if s in pool.films]

    # hard filters
    def keep(f: Film) -> bool:
        if f.rating_count < 25 or (f.runtime and f.runtime < 40):
            return False  # unreleased/too obscure, or shorts
        if is_series(f):
            return False
        if not a["subtitles"] and f.language not in (None, "English", "No spoken language"):
            return False
        if not a["animation"] and "Animation" in f.genres:
            return False
        if a["runtime"] and f.runtime and f.runtime > a["runtime"] + 8:
            return False
        return True

    cand = [s for s in cand if keep(pool.films[s])]
    if not cand:
        return []

    profiles, idf = build_profiles(pool)
    feats = {s: features(pool.films[s]) for s in cand}
    raw = {u: {s: taste(feats[s], profiles.get(u, {}), idf) for s in cand} for u in users}
    # how close each film is to that person's own favourites (1 = as close as a typical favourite): one scale
    # for everyone, so a film one friend merely doesn't mind can't pass for one they'd love
    per_user = {u: _closeness(raw[u]) for u in users}
    for s, who in pool.watchlisted.items():  # saving a film says "I want to see this": at least halfway there,
        for u in who:                        # and taste decides the rest
            if s in per_user.get(u, {}):
                per_user[u][s] = 0.5 + 0.5 * per_user[u][s]
    match = {u: {s: round(50 + 49 * c ** 1.3) for s, c in per_user[u].items()} for u in users}
    seed_maps = {u: {sd.slug: sd for sd in pool.seeds.get(u, []) if sd.weight > 0} for u in users}

    rel = _rank01({s: pool.films[s].rating_count for s in cand})
    fame = {s: 0.5 * popularity(pool.films[s]) + 0.5 * rel[s] for s in cand}
    scored = []
    for s in cand:
        f = pool.films[s]
        tastes = [per_user[u][s] for u in users]
        group_taste = 0.5 * sum(tastes) / n_users + 0.5 * min(tastes)  # nobody should be stuck with it
        moods = [(m, *mood_score(f, m)) for m in a["moods"] if m in MOODS]
        fits = [sc for _, sc, _ in moods]
        wl = len(pool.watchlisted.get(s, ())) / n_users
        # what you'd pick with no mood in mind: your taste, how good it is, whether you saved it
        score = 0.65 * group_taste + 0.25 * quality(f) + 0.1 * wl
        if f.rating:  # nobody wants a 2.3-star film recommended to them, however on-theme it is
            score *= _clamp((f.rating - 2.4) / 0.8, 0.3, 1.0)  # 3.2+ untouched, 2.8 halved
        if a["fame"] == "any":  # tilt a little toward films people have actually heard of
            score *= 0.85 + 0.15 * fame[s]
        if fits:  # a mood is a request, not a nudge: the film has to *be* it. Two moods = a blend of both.
            vibe = math.prod(fits) ** (1 / len(fits))
            score *= 0.05 + 0.95 * vibe ** 2  # steep: a 0.2 fit is ~10x behind a 0.7 fit, whatever your taste
        if a["fame"] != "any":
            score *= 0.3 + 0.7 * fame_fit(fame[s], a["fame"])
        if a["era"] in ERAS and f.year:
            lo, hi = ERAS[a["era"]]
            score *= 1.0 if lo <= f.year <= hi else 0.3
        if a["runtime"] and f.runtime and f.runtime > a["runtime"]:
            score *= 0.7
        if a["source"] == "mix" and s in pool.watchlisted:
            score *= 1.08
        scored.append((score, s, moods, tastes))

    scored.sort(key=lambda x: -x[0])

    # light diversity: don't stack one director
    picked, director_count = [], Counter()
    for score, s, moods, tastes in scored:  # all of them, so "mix" has discoveries to draw on
        f = pool.films[s]
        pen = 0.85 ** sum(director_count[d] for d in f.directors)
        picked.append((score * pen, s, moods, tastes))
        director_count.update(f.directors)
    picked.sort(key=lambda x: -x[0])
    if a["source"] == "mix":  # keep both sources visible: at least one discovery in every three
        w = [x for x in picked if x[1] in pool.watchlisted]
        d = [x for x in picked if x[1] not in pool.watchlisted]
        merged = []
        while w or d:
            need_d = d and (not w or (len(merged) % 3 == 2 and d[0][0] >= 0.4 * picked[0][0]))
            take = d if need_d or (d and w and d[0][0] > w[0][0]) else (w or d)
            merged.append(take.pop(0))
        picked = merged
    picked = picked[:limit]
    top = max((x[0] for x in picked), default=1)

    out, used_seeds = [], Counter()
    for score, s, moods, tastes in picked:
        f = pool.films[s]
        reasons = []
        who = sorted(pool.watchlisted.get(s, ()), key=list(users).index)
        if who:
            if solo:
                reasons.append({"kind": "watchlist", "text": "It's been waiting on your watchlist"})
            elif len(who) == n_users:
                reasons.append({"kind": "watchlist", "text": "On everyone's watchlist"})
            else:
                reasons.append({"kind": "watchlist", "text": f"On {_names([display[u] for u in who])}'s watchlist"})
        because = _because(pool, f, s, users, seed_maps, display, solo, used_seeds)
        if because:
            reasons.append({"kind": "taste", "text": because})
        if not who and not because and s not in pool.discovered:
            chart = next((MOODS[m]["label"] for m in a["moods"] if s in pool.vibe_found.get(m, ())), None)
            if chart and f.rating_count:
                n = f.rating_count
                fans = f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n // 1000}k" if n >= 1000 else str(n)
                reasons.append({"kind": "taste", "text": f"Popular {chart.lower()} pick: {fans} Letterboxd ratings"})
        best_mood = max(moods, key=lambda m: m[1], default=None)
        if best_mood and best_mood[1] > 0.35 and best_mood[2]:
            reasons.append({"kind": "vibe", "text": best_mood[2]})
        out.append({
            "film": f.__dict__,
            "score": round(score / top, 4),
            "match": round(0.6 * sum(match[u][s] for u in users) / n_users + 0.4 * min(match[u][s] for u in users)),
            "members": [{"username": u, "match": match[u][s], "watchlisted": u in who} for u in users],
            "source": "watchlist" if who else "discovery",
            "reasons": reasons,
        })
    return out


def _closeness(raw: dict[str, float]) -> dict[str, float]:
    """raw taste -> 0..1 on a per-person scale: 1 = as strong a fit as this person's top 2% of tonight's options,
    0 = no pull at all (or a push away). Linear in between, so "doesn't mind it" stays far below "would love it"
    for everyone, unlike a rank, where a neutral film can sit in someone's top 20% of a pool built around a friend.
    ponytail: anchored on the candidates, not on favourites; a favourite barely resembles the others for eclectic
    taste, so it made a poor yardstick."""
    vals = sorted(raw.values())
    ref = vals[int(len(vals) * 0.98)] if vals else 1
    ref = ref if ref > 0 else 1
    return {s: _clamp(v / ref) for s, v in raw.items()}


def _because(pool, f, s, users, seed_maps, display, solo, used_seeds) -> str | None:
    """Best 'because you loved X' link, preferring the similar-films graph, then shared director/cast/theme."""
    def loved(u, sd):
        who = "you" if solo else display[u]
        if sd.rating:
            verb = f"rated {'★' * (sd.rating // 2)}{'½' if sd.rating % 2 else ''}"
        else:
            verb = "enjoyed"
        return who, verb

    def pick(score, sd):  # spread the credit around instead of citing one favourite all night
        return score - 0.8 * used_seeds[sd.slug]

    links = [(u, seed) for u, seed in pool.discovered.get(s, []) if seed in seed_maps[u] and seed in pool.films]
    if links:
        u, seed = max(links, key=lambda l: pick(seed_maps[l[0]][l[1]].weight, seed_maps[l[0]][l[1]]))
        used_seeds[seed] += 1
        who, verb = loved(u, seed_maps[u][seed])
        return f"Like {pool.films[seed].title}, which {who} {verb}"
    best = None
    for u in users:
        for sd in seed_maps[u].values():
            g = pool.films.get(sd.slug)
            if not g or g.slug == s or (g.runtime and g.runtime < 40) or is_series(g):
                continue  # "director of Love, Death & Robots: Bad Travelling" is true and useless
            shared_d = set(f.directors) & set(g.directors)
            if shared_d:
                cand = (pick(4 + sd.weight, sd), f"From {next(iter(shared_d))}, director of {g.title}", u, sd)
            else:
                # leads in both, or it's "Stars John Lithgow, from Shrek"
                shared_c = [c for c in f.cast[:3] if c in g.cast[:3]]
                # Letterboxd themes are broad ("Powerful stories of heartbreak"), so it takes three plus a genre
                shared_t = set(f.themes) & set(g.themes) if set(f.genres) & set(g.genres) else set()
                if shared_c:
                    cand = (pick(2.5 + sd.weight, sd), f"Stars {shared_c[0]}, from {g.title}", u, sd)
                elif len(shared_t) >= 3:
                    cand = (pick(len(shared_t) * 0.4 + sd.weight, sd), f"Same territory as {g.title}", u, sd)
                else:
                    continue
            if best is None or cand[0] > best[0]:
                best = cand
    if not best:
        return None
    _, text, u, sd = best
    used_seeds[sd.slug] += 1
    who, verb = loved(u, sd)
    return f"{text}, which {who} {verb}" if not text.startswith("From") else f"{text} ({who} {verb} it)"
