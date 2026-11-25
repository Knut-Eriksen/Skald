"""Gathers a group's data in the background (while they answer the vibe questions)."""
import asyncio
import time
import uuid
from dataclasses import dataclass, field

from . import letterboxd as lb, recommend as rec, tmdb

SEEDS_FOR_SIMILAR = 16  # per user


@dataclass
class Job:
    id: str
    usernames: list[str]
    stage: str = "starting"
    message: str = "Warming up the projector"
    progress: float = 0.0
    error: str | None = None
    pool: rec.Pool | None = None
    created: float = field(default_factory=time.time)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    def update(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.changed.set()

    def snapshot(self):
        return {"id": self.id, "stage": self.stage, "message": self.message,
                "progress": round(self.progress, 3), "error": self.error, "ready": self.pool is not None}


jobs: dict[str, Job] = {}


def start(usernames: list[str]) -> Job:
    key = ",".join(sorted(u.lower() for u in usernames))
    for j in jobs.values():  # reuse a running/finished job for the same group
        if ",".join(sorted(j.usernames)) == key and not j.error and time.time() - j.created < 3600:
            return j
    j = Job(id=uuid.uuid4().hex[:12], usernames=[u.lower() for u in usernames])
    jobs[j.id] = j
    j.task = asyncio.create_task(_run(j))
    return j


async def _run(j: Job):
    try:
        j.pool = await gather(j)
        j.update(stage="ready", message="Ready", progress=1.0)
    except lb.NotFound as e:
        j.update(stage="error", error=f"Couldn't find {e}")
    except lb.Blocked:
        j.update(stage="error", error="Letterboxd is rate-limiting us. Give it a minute and try again.")
    except Exception as e:  # surface anything else to the UI instead of hanging
        j.update(stage="error", error=f"Something went wrong: {e}")
        raise


async def gather(j: Job) -> rec.Pool:
    # 1. lists (0 -> 35%)
    msgs = {}

    def on_user(u):
        def cb(msg):
            msgs[u] = msg
            j.update(stage="lists", message=msg)
        return cb

    users = await asyncio.gather(*(lb.user_data(u, on_user(u)) for u in j.usernames))
    j.update(stage="taste", message="Learning what everyone loves", progress=0.35)

    # 2. seeds + similar films (35 -> 55%)
    seeds = {u.profile.username: rec.pick_seeds(u) for u in users}
    watched = {f.slug for u in users for f in u.watched}
    seed_slugs = {s.slug for ss in seeds.values() for s in ss}
    total, done = len(seed_slugs), 0

    def tick(lo, hi, label):
        def cb():
            nonlocal done
            done += 1
            j.update(progress=lo + (hi - lo) * done / max(total, 1), message=label)
        return cb

    films = await lb.films(seed_slugs, tick(0.35, 0.5, "Studying everyone's favourites"))

    top_seeds = {u: [s.slug for s in ss if s.weight > 0][:SEEDS_FOR_SIMILAR] for u, ss in seeds.items()}
    pairs = [(u, s) for u, ss in top_seeds.items() for s in ss]
    j.update(stage="discover", message="Following the threads between films", progress=0.5)
    sims = await asyncio.gather(*(lb.similar(s, 20) for _, s in pairs))
    similar = dict(zip(pairs, sims))

    if tmdb.KEY:
        tm_pairs = [(u, s) for u, s in pairs if films.get(s) and films[s].tmdb_id][:30]
        recs = await asyncio.gather(*(tmdb.recommendations(films[s].tmdb_id) for _, s in tm_pairs))
        ids = {i for r in recs for i in r}
        slug_of = dict(zip(ids, await asyncio.gather(*(lb.tmdb_to_slug(i) for i in ids))))
        for (u, s), r in zip(tm_pairs, recs):
            extra = [slug_of[i] for i in r if slug_of.get(i)]
            similar[(u, s)] = similar.get((u, s), []) + [x for x in extra if x not in similar.get((u, s), [])]

    discovered = rec.discovery_candidates(similar, watched)
    watchlisted, wl_order = rec.watchlist_candidates(users)
    j.update(progress=0.55)

    # 3. candidate details (55 -> 100%)
    need = [s for s in dict.fromkeys(wl_order + list(discovered)) if s not in films]
    total, done = len(need), 0
    films.update(await lb.films(need, tick(0.55, 0.99, "Pulling posters off the shelf")))
    watchlisted = {s: who for s, who in watchlisted.items() if s in films}

    return rec.Pool(users=list(users), films=films, seeds=seeds, watchlisted=watchlisted,
                    discovered=discovered, watched_any=watched)
