"""Run: .venv/bin/python -m pytest backend  (or: python -m backend.test_recommend)"""
from .letterboxd import Film, ListFilm, Profile, UserData
from .recommend import Pool, mood_score, pick_seeds, recommend, watchlist_candidates


def film(slug, genres, themes=(), runtime=100, lang="English", director="D", rating=3.8, count=50_000, year=2010):
    return Film(slug=slug, title=slug.title(), year=year, tmdb_id=1, genres=list(genres), themes=list(themes),
                runtime=runtime, language=lang, directors=[director], rating=rating, rating_count=count)


def user(name, watched, liked=(), watchlist=()):
    return UserData(Profile(name, name.title(), None, len(watched)), [ListFilm(s, s, r) for s, r in watched],
                    list(liked), list(watchlist))


def make_pool():
    films = {f.slug: f for f in [
        film("heat", ["Crime", "Thriller"], ["Heists and thrilling action"], director="Mann"),
        film("collateral", ["Crime", "Thriller"], ["Heists and thrilling action"], director="Mann"),
        film("thief", ["Crime", "Thriller"], ["Heists and thrilling action"], director="Mann"),
        film("paddington", ["Family", "Comedy"], ["Heartwarming and charming family"], director="King"),
        film("amelie", ["Comedy", "Romance"], ["Whimsical, quirky romance"], lang="French", director="Jeunet"),
        film("long-epic", ["Thriller"], ["Heists and thrilling action"], runtime=200, director="X"),
        film("violent", ["Drama"], ["Intense violence and transgression"], director="Y"),
    ]}
    a = user("ana", [("heat", 10), ("paddington", 3)], liked=["heat"], watchlist=["collateral", "amelie", "long-epic"])
    b = user("bo", [("collateral", None)], watchlist=["thief", "violent", "paddington"])
    users = [a, b]
    watchlisted, _ = watchlist_candidates(users)
    return Pool(users=users, films=films, seeds={u.profile.username: pick_seeds(u) for u in users},
                watchlisted=watchlisted, watched_any={f.slug for u in users for f in u.watched})


def test_recommend():
    pool = make_pool()
    slugs = [p["film"]["slug"] for p in recommend(pool, {"moods": ["tense"]})]
    assert "heat" not in slugs and "collateral" not in slugs, "anything someone watched is out"
    assert slugs[0] == "thief", slugs  # matches Ana's loved Heat (same director) and the tense vibe

    short = [p["film"]["slug"] for p in recommend(pool, {"runtime": 120})]
    assert "long-epic" not in short

    english = [p["film"]["slug"] for p in recommend(pool, {"subtitles": False})]
    assert "amelie" not in english

    wl = recommend(pool, {"source": "watchlist"})
    thief = next(p for p in wl if p["film"]["slug"] == "thief")
    assert thief["reasons"][0]["text"] == "On Bo's watchlist"
    assert any("Mann" in r["text"] for r in thief["reasons"]), thief["reasons"]


def test_moods_feel_human():
    isle = film("isle-of-dogs", ["Comedy", "Animation", "Adventure"], ["Quirky and endearing relationships"],
                runtime=101)
    isle.synopsis = "The outcasts must soon embark on an epic journey."
    lawrence = film("lawrence", ["Adventure", "War", "History"],
                    ["Epic history and literature", "Historical battles and epic heroism"], runtime=228)
    assert mood_score(lawrence, "epic")[0] > 0.8 > 0.5 > mood_score(isle, "epic")[0]

    films = {f.slug: f for f in [isle, lawrence,
                                 film("crime-comedy", ["Crime", "Comedy", "Thriller"], ["Dark crime comedy"]),
                                 film("paddington", ["Family", "Comedy"], ["Heartwarming and charming family"]),
                                 film("big", ["Drama"], count=2_000_000), film("small", ["Drama"], count=4_000)]}
    u = user("ana", [], watchlist=list(films))
    pool = Pool(users=[u], films=films, seeds={"ana": []}, watchlisted=watchlist_candidates([u])[0])
    top = lambda ans: recommend(pool, ans)[0]["film"]["slug"]
    assert top({"moods": ["epic"]}) == "lawrence"  # even though Isle of Dogs matches "epic journey"
    assert top({"moods": ["cozy", "funny"]}) == "paddington"  # two moods = both, not either
    order = lambda ans: [p["film"]["slug"] for p in recommend(pool, ans)]
    gem, popular = order({"fame": "gem"}), order({"fame": "popular"})
    assert gem.index("small") < gem.index("big") and popular.index("big") < popular.index("small")


def test_mood_traps_from_real_data():
    isle = film("isle", ["Comedy", "Animation", "Adventure"], ["Quirky and endearing relationships"])
    assert mood_score(isle, "romantic")[0] <= 0.3  # friendship "relationships" isn't romance
    life_is_beautiful = film("lib", ["Comedy", "Drama"], ["Heartfelt and sentimental family stories",
                                                          "Heartbreaking and moving family drama"])
    assert mood_score(life_is_beautiful, "cozy")[0] < 0.4
    pianist = film("pianist", ["War", "Drama"], ["War and historical adventure", "Nazis and World War II"], runtime=150)
    assert mood_score(pianist, "epic")[0] < 0.4
    procedural = film("mystic", ["Mystery", "Drama", "Thriller", "Crime"], ["Twisted dark psychological thriller"])
    mulholland = film("mulholland", ["Drama", "Mystery", "Thriller"],
                      ["Dreamlike, quirky, and surreal storytelling", "Twisted dark psychological thriller"])
    assert mood_score(mulholland, "mindbend")[0] > mood_score(procedural, "mindbend")[0] + 0.3

    films = {"good": film("good", ["Drama"], ["Dreamlike, quirky, and surreal storytelling"], rating=3.9),
             "dud": film("dud", ["Drama"], ["Dreamlike, quirky, and surreal storytelling",
                                            "Surreal and thought-provoking visions"], rating=2.3)}
    u = user("ana", [], watchlist=list(films))
    pool = Pool(users=[u], films=films, seeds={"ana": []}, watchlisted=watchlist_candidates([u])[0])
    assert recommend(pool, {"moods": ["mindbend"]})[0]["film"]["slug"] == "good"  # 2.3 stars sinks


def test_new_blockbuster_is_not_a_gem():
    from .recommend import popularity
    new_hit = film("heart-of-the-beast", ["Adventure"], count=246_000, year=2026)
    old_cult = film("cult", ["Adventure"], count=246_000, year=1985)
    assert popularity(new_hit) > 0.9 > popularity(old_cult)


def test_mix_keeps_new_finds():
    films = {f"w{i}": film(f"w{i}", ["Adventure"], ["Epic adventure"], rating=4.2, director=f"w{i}") for i in range(12)}
    films |= {f"d{i}": film(f"d{i}", ["Adventure"], ["Epic adventure"], rating=3.6, director=f"d{i}") for i in range(12)}
    u = user("ana", [], watchlist=[s for s in films if s[0] == "w"])
    pool = Pool(users=[u], films=films, seeds={"ana": []}, watchlisted=watchlist_candidates([u])[0],
                discovered={s: [] for s in films if s[0] == "d"})
    picks = recommend(pool, {"moods": ["epic"], "source": "mix"}, limit=9)
    assert sum(p["source"] == "discovery" for p in picks) >= 3  # watchlist films are better rated, finds still show


def test_mood_word_boundaries():
    assert mood_score(film("v", ["Drama"], ["Intense violence"]), "tense")[0] == 0  # "tense" ≠ "intense"
    assert mood_score(film("p", ["Family"], ["Heartwarming and charming family"]), "cozy")[0] > 0.6


if __name__ == "__main__":
    test_recommend()
    test_moods_feel_human()
    test_mood_traps_from_real_data()
    test_new_blockbuster_is_not_a_gem()
    test_mix_keeps_new_finds()
    test_mood_word_boundaries()
    print("ok")
