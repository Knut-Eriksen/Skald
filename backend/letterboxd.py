"""Letterboxd scraping: user lists, profiles, film details, similar films, availability.

Plain HTTP (no browser). curl_cffi impersonates Chrome's TLS fingerprint, which
gets through Cloudflare where `requests` gets a "Just a moment..." page.
"""
import asyncio
import html
import json
import re
from dataclasses import dataclass, field, asdict

from curl_cffi.requests import AsyncSession
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from . import cache

BASE = "https://letterboxd.com"
CONCURRENCY = 8  # ponytail: global limiter; per-host politeness tuning if Letterboxd starts throttling
MAX_LIST_PAGES = 80  # ~5.7k films; anyone bigger gets truncated

USER_TTL = 6 * 3600
FILM_TTL = 30 * 86400
AVAIL_TTL = 86400

_sem = asyncio.Semaphore(CONCURRENCY)
_session: AsyncSession | None = None


class NotFound(Exception):
    pass


class Blocked(Exception):
    pass


def _s() -> AsyncSession:
    global _session
    if _session is None:
        _session = AsyncSession(impersonate="chrome", timeout=25)
    return _session


async def fetch(path: str) -> str:
    """GET a Letterboxd path with retries. Raises NotFound on 404."""
    url = path if path.startswith("http") else BASE + path
    delay = 1.0
    for attempt in range(5):
        async with _sem:
            try:
                r = await _s().get(url, allow_redirects=True)
            except Exception:
                if attempt == 4:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
                continue
        if r.status_code == 404:
            raise NotFound(url)
        if r.status_code == 200 and "<title>Just a moment" not in r.text[:3000]:
            return r.text
        # 403 challenge / 429 / 5xx: back off and retry
        await asyncio.sleep(delay)
        delay *= 2
    raise Blocked(f"Letterboxd refused {url} (status {r.status_code})")


# ---------------------------------------------------------------- user data


@dataclass
class ListFilm:
    slug: str
    name: str
    rating: int | None = None  # half-stars 1..10


@dataclass
class Profile:
    username: str
    display_name: str
    avatar: str | None
    films_count: int


def _parse_grid(doc: HTMLParser) -> list[ListFilm]:
    out = []
    for li in doc.css("li.griditem, li.poster-container"):
        node = li.css_first("[data-item-slug]") or li.css_first("[data-film-slug]")
        if not node:
            continue
        a = node.attributes
        slug = a.get("data-item-slug") or a.get("data-film-slug")
        name = html.unescape(a.get("data-item-name") or a.get("data-film-name") or slug)
        rating = None
        r = li.css_first(".rating")
        if r:
            m = re.search(r"rated-(\d+)", r.attributes.get("class", ""))
            if m:
                rating = int(m.group(1))
        out.append(ListFilm(slug, name, rating))
    return out


def _last_page(doc: HTMLParser) -> int:
    pages = [int(a.text(strip=True)) for a in doc.css(".paginate-page a") if a.text(strip=True).isdigit()]
    return max(pages, default=1)


async def _list_pages(path: str, progress=None) -> list[ListFilm]:
    """All films in a paginated grid (films/, likes/films/, watchlist/)."""
    first = HTMLParser(await fetch(path))
    films = _parse_grid(first)
    last = min(_last_page(first), MAX_LIST_PAGES)
    if last > 1:
        done = 1

        async def page(n):
            nonlocal done
            p = _parse_grid(HTMLParser(await fetch(f"{path}page/{n}/")))
            done += 1
            if progress:
                progress(done, last)
            return p

        for p in await asyncio.gather(*(page(n) for n in range(2, last + 1))):
            films.extend(p)
    # dedupe, keep order (page shifts during scraping can duplicate)
    seen, out = set(), []
    for f in films:
        if f.slug not in seen:
            seen.add(f.slug)
            out.append(f)
    return out


def _num(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s) or 0)


async def profile(username: str) -> Profile:
    key = f"profile:{username.lower()}"
    if hit := cache.get(key, USER_TTL):
        return Profile(**hit)
    doc = HTMLParser(await fetch(f"/{username}/"))
    if "profile" not in (doc.css_first("title").text() if doc.css_first("title") else "").lower():
        raise NotFound(username)
    name_node = doc.css_first(".person-display-name .displayname .label, .person-display-name .displayname")
    display = name_node.text(strip=True) if name_node else username
    img = doc.css_first(".profile-avatar img, .avatar.-a110 img, .avatar.-large img")
    avatar = img.attributes.get("src") if img else None
    if avatar and "static/img/" in avatar:  # default silhouette
        avatar = None
    films_count = 0
    for h in doc.css(".profile-statistic"):
        d = h.css_first(".definition")
        v = h.css_first(".value")
        if d and v and d.text(strip=True).lower() == "films":
            films_count = _num(v.text())
    p = Profile(username=username.lower(), display_name=display or username, avatar=avatar, films_count=films_count)
    cache.set(key, asdict(p))
    return p


@dataclass
class UserData:
    profile: Profile
    watched: list[ListFilm]
    liked: list[str]
    watchlist: list[str]


async def user_data(username: str, progress=None) -> UserData:
    """Everything we need about one user. progress(msg) gets human-readable updates."""
    u = username.lower()
    prof = await profile(u)
    key = f"userdata:{u}"
    if hit := cache.get(key, USER_TTL):
        return UserData(prof, [ListFilm(**f) for f in hit["watched"]], hit["liked"], hit["watchlist"])

    def p(label):
        return (lambda d, t: progress(f"Reading {prof.display_name}'s {label} · page {d} of {t}")) if progress else None

    if progress:
        progress(f"Reading {prof.display_name}'s {prof.films_count:,} films")
    watched, liked, watchlist = await asyncio.gather(
        _list_pages(f"/{u}/films/", p("diary")),
        _list_pages(f"/{u}/likes/films/", p("likes")),
        _list_pages(f"/{u}/watchlist/", p("watchlist")),
    )
    data = UserData(prof, watched, [f.slug for f in liked], [f.slug for f in watchlist])
    cache.set(key, {"watched": [asdict(f) for f in watched], "liked": data.liked, "watchlist": data.watchlist})
    return data


# ---------------------------------------------------------------- films


@dataclass
class Film:
    slug: str
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    poster: str | None = None
    backdrop: str | None = None
    synopsis: str = ""
    tagline: str = ""
    directors: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    language: str | None = None
    runtime: int | None = None
    rating: float | None = None
    rating_count: int = 0
    trailer: str | None = None


def _ld_json(doc: HTMLParser) -> dict:
    for s in doc.css('script[type="application/ld+json"]'):
        txt = re.sub(r"/\*.*?\*/", "", s.text(), flags=re.S).strip()
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            continue
    return {}


def _sluglist_after(doc: HTMLParser, panel: str, heading: str) -> list[str]:
    """Texts of links under an <h3>heading</h3> inside a tab panel."""
    root = doc.css_first(f"#{panel}")
    if not root:
        return []
    out, grab = [], False
    for node in root.iter():
        if node.tag == "h3":
            grab = node.text(strip=True).lower().startswith(heading.lower())
        elif grab and node.tag == "div":
            out = [a.text(strip=True) for a in node.css("a") if "show all" not in a.text(strip=True).lower()]
            break
    return out


def parse_film(slug: str, page: str) -> Film:
    doc = HTMLParser(page)
    ld = _ld_json(doc)
    title_node = doc.css_first("h1.primaryname .name, h1.headline-1")
    title = title_node.text(strip=True) if title_node else ld.get("name", slug)
    year = None
    y = doc.css_first(".releasedate a, .releaseyear a")
    if y and y.text(strip=True).isdigit():
        year = int(y.text(strip=True))
    body = doc.body
    tmdb = body.attributes.get("data-tmdb-id") if body else None
    if not tmdb:
        m = re.search(r'data-tmdb-id="(\d+)"', page)
        tmdb = m.group(1) if m else None
    og = doc.css_first('meta[property="og:image"]')
    backdrop = og.attributes.get("content") if og else None
    # og:image falls back to the poster when a film has no backdrop; posters are portrait crops
    if backdrop and "film-poster" in backdrop:
        backdrop = None
    runtime = None
    if m := re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?", ld.get("duration", "") or ""):
        if m.group(1) or m.group(2):
            runtime = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    if runtime is None and (m := re.search(r"(\d+)&nbsp;mins", page)):
        runtime = int(m.group(1))
    agg = ld.get("aggregateRating") or {}
    trailer = None
    t = doc.css_first(".js-watch-panel-trailer a, a.js-video-zoom")
    if t and "youtube" in (t.attributes.get("href") or ""):
        trailer = "https:" + t.attributes["href"] if t.attributes["href"].startswith("//") else t.attributes["href"]
    tagline_node = doc.css_first(".review .tagline, h4.tagline")
    desc_node = doc.css_first(".review .truncate p, .film-text-summary p, div.truncate p")
    synopsis = desc_node.text(strip=True) if desc_node else ld.get("description", "")
    cast = [a.text(strip=True) for a in doc.css("#tab-panel-cast .cast-list a.text-slug")][:8]
    languages = _sluglist_after(doc, "tab-panel-details", "Primary Language") or _sluglist_after(
        doc, "tab-panel-details", "Language"
    )
    return Film(
        slug=slug,
        title=html.unescape(title),
        year=year,
        tmdb_id=int(tmdb) if tmdb else None,
        poster=ld.get("image"),
        backdrop=backdrop,
        synopsis=html.unescape(synopsis or ""),
        tagline=tagline_node.text(strip=True) if tagline_node else "",
        directors=[d["name"] for d in ld.get("director", []) if isinstance(d, dict)],
        cast=cast or [a["name"] for a in ld.get("actor", [])[:8] if isinstance(a, dict)],
        genres=_sluglist_after(doc, "tab-panel-genres", "Genre"),
        themes=_sluglist_after(doc, "tab-panel-genres", "Theme"),
        countries=_sluglist_after(doc, "tab-panel-details", "Countr"),
        language=languages[0] if languages else None,
        runtime=runtime,
        rating=agg.get("ratingValue"),
        rating_count=agg.get("ratingCount") or 0,
        trailer=trailer,
    )


async def film(slug: str) -> Film | None:
    key = f"film:{slug}"
    if hit := cache.get(key, FILM_TTL):
        return Film(**hit)
    try:
        f = parse_film(slug, await fetch(f"/film/{slug}/"))
    except (NotFound, Blocked):
        return None
    cache.set(key, asdict(f))
    return f


async def films(slugs, on_done=None) -> dict[str, Film]:
    async def one(s):
        f = await film(s)
        if on_done:
            on_done()
        return s, f

    return {s: f for s, f in await asyncio.gather(*(one(s) for s in slugs)) if f}


async def similar(slug: str, limit: int = 24) -> list[str]:
    key = f"similar:{slug}"
    if (hit := cache.get(key, FILM_TTL)) is not None:
        return hit[:limit]
    try:
        doc = HTMLParser(await fetch(f"/film/{slug}/similar/"))
    except (NotFound, Blocked):
        return []
    out = [f.slug for f in _parse_grid(doc) if f.slug != slug]
    cache.set(key, out)
    return out[:limit]


async def tmdb_to_slug(tmdb_id: int) -> str | None:
    """Letterboxd redirects /tmdb/<id>/ to the film page."""
    key = f"tmdbslug:{tmdb_id}"
    if (hit := cache.get(key, FILM_TTL)) is not None:
        return hit or None
    try:
        page = await fetch(f"/tmdb/{tmdb_id}/")
    except (NotFound, Blocked):
        cache.set(key, "")
        return None
    m = re.search(r'<meta property="og:url" content="https://letterboxd\.com/film/([^/]+)/"', page)
    slug = m.group(1) if m else ""
    if slug and not cache.get(f"film:{slug}", FILM_TTL):
        cache.set(f"film:{slug}", asdict(parse_film(slug, page)))
    cache.set(key, slug)
    return slug or None


async def availability(slug: str) -> dict:
    """Where to watch (localized by Letterboxd/JustWatch to the server's IP country)."""
    key = f"avail:{slug}"
    if (hit := cache.get(key, AVAIL_TTL)) is not None:
        return hit
    try:
        doc = HTMLParser(await fetch(f"/csi/film/{slug}/availability/?esiAllowUser=true&esiAllowCountry=true"))
    except (NotFound, Blocked):
        return {"services": [], "country": None}
    services, country = [], None
    for p in doc.css("section.services p.service"):
        label = p.css_first("a.label")
        if not label:
            continue
        name = p.css_first(".name")
        loc = p.css_first(".locale")
        img = p.css_first("img")
        kinds = []
        for o in p.css(".options a"):
            cls = o.attributes.get("class", "")
            kind = next((k for k in ("stream", "rent", "buy", "free", "ads") if f"-{k}" in cls), None)
            if kind and kind not in kinds:
                kinds.append(kind)
        country = country or (loc.text(strip=True) if loc else None)
        if not name or not name.text(strip=True) or any(x["name"] == name.text(strip=True) for x in services):
            continue
        services.append(
            {
                "name": name.text(strip=True) if name else "",
                "icon": img.attributes.get("src") if img else None,
                "url": label.attributes.get("href"),
                "kinds": kinds,
            }
        )
    out = {"services": services, "country": country}
    cache.set(key, out)
    return out
