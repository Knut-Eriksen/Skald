import asyncio
import json
import re
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import engine, letterboxd as lb, recommend as rec

app = FastAPI(title="Reel")
DIST = Path(__file__).parent.parent / "frontend" / "dist"
USERNAME = re.compile(r"^[A-Za-z0-9_]{2,40}$")

# Hero art for the landing page (slugs on Letterboxd).
BACKDROPS = ["in-the-mood-for-love", "blade-runner-2049", "past-lives", "spirited-away", "the-grand-budapest-hotel",
             "parasite-2019", "lawrence-of-arabia", "aftersun", "mad-max-fury-road", "portrait-of-a-lady-on-fire",
             "2001-a-space-odyssey", "moonlight-2016", "the-shining", "la-la-land", "dune-part-two",
             "perfect-days-2023"]


def _check(username: str) -> str:
    if not USERNAME.match(username):
        raise HTTPException(400, "That doesn't look like a Letterboxd username")
    return username.lower()


@app.get("/api/user/{username}")
async def user(username: str):
    try:
        return asdict(await lb.profile(_check(username)))
    except lb.NotFound:
        raise HTTPException(404, f"No Letterboxd user called “{username}”")
    except lb.Blocked:
        raise HTTPException(503, "Letterboxd is rate-limiting us, try again in a moment")


class StartBody(BaseModel):
    usernames: list[str] = Field(min_length=1, max_length=8)


@app.post("/api/jobs")
async def start_job(body: StartBody):
    j = engine.start([_check(u) for u in dict.fromkeys(u.lower() for u in body.usernames)])
    return j.snapshot()


def _job(job_id: str) -> engine.Job:
    if job_id not in engine.jobs:
        raise HTTPException(404, "Session expired, start again")
    return engine.jobs[job_id]


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    j = _job(job_id)

    async def stream():
        while True:
            yield f"data: {json.dumps(j.snapshot())}\n\n"
            if j.pool is not None or j.error:
                return
            j.changed.clear()
            try:
                await asyncio.wait_for(j.changed.wait(), 15)
            except asyncio.TimeoutError:
                pass  # heartbeat

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class RecommendBody(BaseModel):
    answers: dict = {}
    limit: int = Field(30, ge=1, le=60)


@app.post("/api/jobs/{job_id}/recommend")
async def recommend(job_id: str, body: RecommendBody):
    j = _job(job_id)
    if j.task and not j.pool and not j.error:
        await asyncio.shield(j.task)
    if j.error:
        raise HTTPException(502, j.error)
    pool = j.pool
    picks = rec.recommend(pool, body.answers, body.limit)
    return {
        "picks": picks,
        "members": [
            {**asdict(u.profile), "watched": len(u.watched), "liked": len(u.liked), "watchlist": len(u.watchlist)}
            for u in pool.users
        ],
        "stats": {"considered": len(pool.films), "watchlisted": len(pool.watchlisted),
                  "discovered": len(pool.discovered)},
    }


@app.get("/api/film/{slug}/availability")
async def availability(slug: str):
    if not re.match(r"^[a-z0-9-]+$", slug):
        raise HTTPException(400, "bad slug")
    return await lb.availability(slug)


@app.get("/api/backdrops")
async def backdrops():
    films = await lb.films(BACKDROPS)
    return [{"slug": f.slug, "title": f.title, "year": f.year, "backdrop": f.backdrop}
            for s in BACKDROPS if (f := films.get(s)) and f.backdrop]


@app.get("/api/moods")
def moods():
    return [{"id": k, "label": v["label"]} for k, v in rec.MOODS.items()]


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
