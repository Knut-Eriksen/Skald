"""Pure recommendation logic: seeds -> taste profiles -> scored, explained picks.

No I/O in here, so it is fast enough to re-score live while the vibe is tweaked.
"""
import math
import re
from functools import lru_cache
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .letterboxd import Film, UserData

# ---------------------------------------------------------------- vibe vocabulary

MOODS = {
    "cozy": {
        "label": "Cozy & warm",
        "genres": {"Comedy": 0.6, "Family": 0.9, "Animation": 0.8, "Romance": 0.5},
        "kw": ["heartwarming", "feel-good", "charming", "wholesome", "cozy", "sweet", "touching", "friendship",
               "whimsical", "delightful", "uplifting", "endearing", "gentle", "comforting", "heartfelt"],
        "anti": ["horror", "gore", "violent", "disturbing", "brutal", "terrifying", "grisly"],
    },
    "tense": {
        "label": "Edge of your seat",
        "genres": {"Thriller": 1.0, "Crime": 0.7, "Action": 0.6, "Mystery": 0.6},
        "kw": ["tense", "suspense", "gripping", "thrilling", "heist", "chase", "nerve", "survival",
               "conspiracy", "espionage", "spy", "cat-and-mouse", "pulse", "high-stakes", "adrenaline"],
        "anti": ["heartwarming", "whimsical", "wholesome"],
    },
    "funny": {
        "label": "Laugh out loud",
        "genres": {"Comedy": 1.0},
        "kw": ["funny", "hilarious", "comedy", "comedic", "witty", "quirky", "absurd", "satire", "humor",
               "humour", "laugh", "slapstick", "outrageous", "zany", "raunchy", "parody", "deadpan"],
        "anti": ["tragic", "heartbreaking", "grief", "suffering", "bleak"],
    },
    "emotional": {
        "label": "Wreck me",
        "genres": {"Drama": 0.8, "Romance": 0.5},
        "kw": ["moving", "heartbreak", "tragic", "emotional", "tear", "grief", "loss", "sad", "poignant",
               "touching", "sentimental", "melancholy", "devastating", "suffering", "mourning", "powerful"],
        "anti": ["slapstick", "zany", "raunchy"],
    },
    "mindbend": {
        "label": "Mind-bending",
        "genres": {"Science Fiction": 0.8, "Mystery": 0.7, "Thriller": 0.4},
        "kw": ["mind-bending", "twist", "surreal", "dream", "reality", "time travel", "puzzle", "philosophical",
               "existential", "mysterious", "cerebral", "psychological", "enigmatic", "paranoia", "identity",
               "memory", "simulation", "dystopia", "thought-provoking"],
        "anti": ["slapstick", "wholesome"],
    },
    "dark": {
        "label": "Dark & unsettling",
        "genres": {"Horror": 1.0, "Thriller": 0.5},
        "kw": ["horror", "terrifying", "creepy", "disturbing", "eerie", "haunting", "dread", "supernatural",
               "gore", "nightmare", "sinister", "bleak", "unsettling", "macabre", "chilling", "scary", "demonic",
               "slasher", "grisly"],
        "anti": ["heartwarming", "wholesome", "feel-good", "whimsical"],
    },
    "epic": {
        "label": "Epic escape",
        "genres": {"Adventure": 1.0, "Fantasy": 0.8, "Science Fiction": 0.6, "War": 0.5, "Action": 0.5,
                   "History": 0.4},
        "kw": ["epic", "adventure", "quest", "journey", "spectacular", "battle", "kingdom", "galaxy", "legend",
               "heroic", "sweeping", "grand", "space", "mythical", "monster", "superhero", "empire"],
        "anti": [],
    },
    "romantic": {
        "label": "Swoon",
        "genres": {"Romance": 1.0},
        "kw": ["romance", "romantic", "love", "passion", "relationship", "lovers", "falling in love", "desire",
               "captivating relationships", "courtship"],
        "anti": ["gore", "slasher", "terrifying"],
    },
    "artful": {
        "label": "Dreamy & artful",
        "genres": {"Drama": 0.4, "Fantasy": 0.3},
        "kw": ["beautiful", "poetic", "dreamlike", "atmospheric", "visually", "stunning", "contemplative",
               "meditative", "lyrical", "artistic", "beauty", "mesmerizing", "surreal", "quiet", "ethereal",
               "elegant"],
        "anti": ["slapstick", "raunchy", "superhero"],
    },
    "true": {
        "label": "Real stories",
        "genres": {"Documentary": 1.0, "History": 0.6},
        "kw": ["true story", "documentary", "biography", "biopic", "real-life", "historical", "based on",
               "inspiring", "politics", "journalism", "musician", "legacy"],
        "anti": ["supernatural", "superhero", "fantasy"],
    },
}

ERAS = {"new": (2015, 9999), "modern": (1990, 2014), "classic": (0, 1989)}

DEFAULT_ANSWERS = {
    "moods": [],          # up to 2 MOODS keys; empty = anything
    "runtime": None,      # max minutes or None
    "era": "any",         # ERAS key or "any"
    "fame": "any",        # "popular" | "between" | "gem" | "any"
    "source": "mix",      # "watchlist" | "mix" | "discover"
    "subtitles": True,    # False = English-language only
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
    liked: bool
    rating: int | None


def pick_seeds(u: UserData, n_pos: int = 40, n_neg: int = 10) -> list[Seed]:
    """The films that best describe a user's taste: liked / highly rated, recent first."""
    liked = set(u.liked)
    total = max(len(u.watched), 1)
    scored, neg = [], []
    for i, f in enumerate(u.watched):
        recency = 1 - i / total
        is_liked = f.slug in liked
        r = f.rating
        if r is not None and r <= 4 and not is_liked:
            neg.append(Seed(f.slug, -0.6, False, r))
            continue
        if is_liked or (r is not None and r >= 7):
            score = 2 * is_liked + max(0, (r or 0) - 6) / 2 + recency
            w = 0.6 + 0.4 * is_liked + max(0, (r or 0) - 6) / 8
            scored.append((score, Seed(f.slug, w, is_liked, r)))
    # liked films that were never logged (likes page only)
    watched_slugs = {f.slug for f in u.watched}
    for s in u.liked:
        if s not in watched_slugs:
            scored.append((2.0, Seed(s, 1.0, True, None)))
    scored.sort(key=lambda x: -x[0])
    pos = [s for _, s in scored[:n_pos]]
    if len(pos) < 15:  # sparse profile: lean on whatever they watched recently
        have = {s.slug for s in pos} | {s.slug for s in neg}
        pos += [Seed(f.slug, 0.4, False, f.rating) for f in u.watched if f.slug not in have][: 25 - len(pos)]
    return pos + neg[:n_neg]


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


def discovery_candidates(similar: dict[tuple[str, str], list[str]], watched: set[str], cap: int = 160):
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
    themes, syn = _text(f)
    genre = max((m["genres"].get(g, 0) for g in f.genres), default=0)
    th = _count(m["kw"], themes)
    sy = _count(m["kw"], syn)
    kw = _clamp((th + 0.4 * sy) / 2.2)
    anti = _count(m["anti"], themes) * 0.3
    hits = [(_count(m["kw"], t.lower()) - _count(m["anti"], t.lower()), -i, t) for i, t in enumerate(f.themes)]
    best = max(hits, default=(0, 0, None))
    return _clamp(0.5 * genre + 0.5 * kw - anti), best[2] if best[0] > 0 else None


def popularity(f: Film) -> float:
    return _clamp((math.log10(f.rating_count + 1) - 3.5) / 2.6)  # ~3k ratings -> 0, ~1.2M -> 1


def fame_fit(f: Film, fame: str) -> float:
    p = popularity(f)
    return {"popular": p, "gem": 1 - p, "between": 1 - abs(p - 0.5) * 1.6}.get(fame, 0.6)


def quality(f: Film) -> float:
    return _clamp((f.rating - 2.8) / 1.6) if f.rating else 0.35


def build_profiles(pool: Pool) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Per-user feature weights and an IDF table over every film we know."""
    df = Counter()
    feats = {s: features(f) for s, f in pool.films.items()}
    for fv in feats.values():
        df.update(fv.keys())
    n = max(len(feats), 1)
    idf = {k: math.log(1 + n / (1 + c)) for k, c in df.items()}
    profiles = {}
    for user, seeds in pool.seeds.items():
        prof = defaultdict(float)
        for sd in seeds:
            for k, w in feats.get(sd.slug, {}).items():
                prof[k] += sd.weight * w
        profiles[user] = dict(prof)
    return profiles, idf


def taste(fv: dict[str, float], prof: dict[str, float], idf: dict[str, float]) -> float:
    num = sum(prof.get(k, 0) * w * idf.get(k, 1) for k, w in fv.items())
    den = math.sqrt(sum((w * idf.get(k, 1)) ** 2 for k, w in fv.items())) or 1
    return num / den


def _rank01(values: dict[str, float]) -> dict[str, float]:
    """Percentile rank in [0, 1] (robust to wildly different profile scales)."""
    order = sorted(values, key=values.get)
    n = max(len(order) - 1, 1)
    return {s: i / n for i, s in enumerate(order)}


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]


def recommend(pool: Pool, answers: dict | None = None, limit: int = 30) -> list[dict]:
    a = {**DEFAULT_ANSWERS, **(answers or {})}
    users = {u.profile.username: u for u in pool.users}
    display = {k: u.profile.display_name for k, u in users.items()}
    n_users = len(users)
    solo = n_users == 1

    if a["source"] == "watchlist":
        cand = set(pool.watchlisted)
    elif a["source"] == "discover":
        cand = set(pool.discovered) - set(pool.watchlisted)
    else:
        cand = set(pool.watchlisted) | set(pool.discovered)
    cand = [s for s in cand - pool.watched_any if s in pool.films]

    # hard filters
    def keep(f: Film) -> bool:
        if f.rating_count < 25 or (f.runtime and f.runtime < 40):
            return False  # unreleased/too obscure, or shorts
        if f.runtime and (f.runtime > 240 or (f.tmdb_id is None and f.runtime > 150)):
            return False  # miniseries: Letterboxd lists them as films but TMDB has no movie id
        if not a["subtitles"] and f.language not in (None, "English", "No spoken language"):
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
    per_user = {u: _rank01(raw[u]) for u in users}
    match = {u: _calibrated(raw[u], pool, u, profiles.get(u, {}), idf) for u in users}
    seed_maps = {u: {sd.slug: sd for sd in pool.seeds.get(u, []) if sd.weight > 0} for u in users}

    scored = []
    for s in cand:
        f = pool.films[s]
        tastes = [per_user[u][s] for u in users]
        group_taste = 0.6 * sum(tastes) / n_users + 0.4 * min(tastes)  # nobody should hate it
        moods = [(m, *mood_score(f, m)) for m in a["moods"] if m in MOODS]
        vibe = max((sc for _, sc, _ in moods), default=0.5)
        wl = len(pool.watchlisted.get(s, ())) / n_users
        mult = 1.0
        if a["era"] in ERAS and f.year:
            lo, hi = ERAS[a["era"]]
            mult *= 1.0 if lo <= f.year <= hi else 0.4
        if a["runtime"] and f.runtime and f.runtime > a["runtime"]:
            mult *= 0.7
        if a["source"] == "mix" and s in pool.watchlisted:
            mult *= 1.08
        score = (0.33 * group_taste + 0.27 * vibe + 0.14 * quality(f) + 0.14 * wl + 0.12 * fame_fit(f, a["fame"])) * mult
        scored.append((score, s, moods, tastes))

    scored.sort(key=lambda x: -x[0])

    # light diversity: don't stack one director
    picked, director_count = [], Counter()
    for score, s, moods, tastes in scored[: limit * 4]:
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
            strong_d = d and d[0][0] >= 0.8 * picked[0][0]
            need_d = d and (not w or (strong_d and len(merged) % 3 == 2
                                      and all(m[1] in pool.watchlisted for m in merged[-2:])))
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


def _calibrated(raw: dict[str, float], pool: Pool, u: str, prof, idf) -> dict[str, int]:
    """Map raw taste to a 50-99 'match %': 99 ~= as close as the user's own favourites."""
    favs = sorted(taste(features(pool.films[sd.slug]), prof, idf)
                  for sd in pool.seeds.get(u, []) if sd.weight > 0 and sd.slug in pool.films)
    ref = favs[int(len(favs) * 0.6)] if favs else max(raw.values(), default=1)
    ref = ref if ref > 0 else 1
    return {s: round(50 + 49 * _clamp(v / ref) ** 1.3) for s, v in raw.items()}


def _because(pool, f, s, users, seed_maps, display, solo, used_seeds) -> str | None:
    """Best 'because you loved X' link, preferring the similar-films graph, then shared director/cast/theme."""
    def loved(u, sd):
        who = "you" if solo else display[u]
        if sd.liked:
            verb = "loved"
        elif sd.rating:
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
            if not g or g.slug == s:
                continue
            shared_d = set(f.directors) & set(g.directors)
            if shared_d:
                cand = (pick(4 + sd.weight, sd), f"From {next(iter(shared_d))}, director of {g.title}", u, sd)
            else:
                shared_c = [c for c in f.cast[:4] if c in g.cast[:6]]
                shared_t = set(f.themes) & set(g.themes)
                if shared_c:
                    cand = (pick(2.5 + sd.weight, sd), f"Stars {shared_c[0]}, from {g.title}", u, sd)
                elif len(shared_t) >= 2:
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
