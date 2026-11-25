# Skald

**The film everyone wants to watch.** Add one or more Letterboxd usernames, pick a mood and how much time you have, and Skald picks tonight's film. It knows what everyone has already seen, what they loved, and what's been sitting on their watchlists.

## Run it

```bash
git clone https://github.com/Knut-Eriksen/Skald.git
cd Skald
python3 run.py
```

That's it. The first run creates a virtualenv, installs the Python packages, builds the interface (needs Node.js 18+) and opens http://localhost:8000.

Optional: copy `.env.example` to `.env` and add a free [TMDB](https://www.themoviedb.org/settings/api) key for extra discovery.

## How it works

1. **Read.** As soon as you press Continue, the backend starts reading every member's diary (ratings), likes and watchlist straight from Letterboxd while you answer the questions.
2. **Learn taste.** For each person it picks the ~40 films that define them (likes, 4★+, recent first) plus the ones they panned, and builds a weighted profile of genres, Letterboxd themes, directors, cast, countries and decades (TF-IDF weighted).
3. **Gather candidates.**
   - *Watchlists:* everything on anyone's watchlist that nobody has seen. Films on several watchlists come first.
   - *New finds:* Letterboxd's "similar films" for everyone's favourites, ranked by how many favourites (and people) point at them. With a TMDB key, TMDB recommendations are added too.
   - *Vibe charts:* once you pick a mood (and era), the matching Letterboxd genre charts are fetched in the background, so "Epic adventure" can surface epics even for a group of drama fans.
4. **Score.** Each candidate gets: group taste (average blended with the *least* happy member, so nobody gets stuck with something they'd hate) + vibe fit (genre and theme keywords) + Letterboxd rating + watchlist overlap + crowd-pleaser vs hidden-gem fit. Runtime, era and subtitles filter the list. A director-diversity pass stops one filmmaker from taking over the list.
5. **Explain.** Every pick says *why*: who has it on their watchlist, which loved film it connects to ("From Park Chan-wook, director of Oldboy"), and which theme matches the mood.

Results come with the trailer, streaming/rent options for your country (via Letterboxd/JustWatch), a per-person match score, an **Adjust the vibe** drawer that re-ranks instantly, and a **Streaming now** filter that hides anything you'd have to rent.

## Notes

- Profiles must be public. Private watchlists are simply skipped.
- Everything is cached in `cache.sqlite3` (user data for 6 h, film details for 30 days), so the second run for the same group is instant. Delete the file to start fresh.
- First run for a big profile (3–5k films) takes ~20–40 s, mostly hidden behind the questions.
- Keyboard: `1`–`9`/`0` pick answers, `Enter` next, `←` back; on results `T` plays the trailer, `N` skips.

## Development

```bash
.venv/bin/uvicorn backend.app:app --reload      # API on :8000
cd frontend && npm run dev                       # UI on :5173 (proxies /api)
.venv/bin/python -m backend.test_recommend       # recommender self-check
```

```
backend/
  letterboxd.py   scraping (curl_cffi impersonates Chrome to get past Cloudflare)
  recommend.py    pure scoring + explanations
  engine.py       background data gathering with progress events
  app.py          FastAPI: REST + server-sent events, serves the built UI
  tmdb.py         optional extra discovery
frontend/         Vite + React + TypeScript + Motion
run.py            one-command launcher
```

This scrapes public Letterboxd pages for personal use. Be gentle (requests are rate-limited and cached).
