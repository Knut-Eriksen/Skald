export type Profile = { username: string; display_name: string; avatar: string | null; films_count: number }

export type Film = {
  slug: string
  title: string
  year: number | null
  poster: string | null
  backdrop: string | null
  synopsis: string
  tagline: string
  directors: string[]
  cast: string[]
  genres: string[]
  themes: string[]
  countries: string[]
  language: string | null
  runtime: number | null
  rating: number | null
  rating_count: number
  trailer: string | null
}

export type Reason = { kind: 'watchlist' | 'taste' | 'vibe'; text: string }

export type Pick = {
  film: Film
  score: number
  match: number
  members: { username: string; match: number; watchlisted: boolean }[]
  source: 'watchlist' | 'discovery'
  reasons: Reason[]
}

export type Member = Profile & { watched: number; liked: number; watchlist: number }

export type Results = {
  picks: Pick[]
  members: Member[]
  stats: { considered: number; watchlisted: number; discovered: number }
}

export type JobState = {
  id: string
  stage: string
  message: string
  progress: number
  error: string | null
  ready: boolean
}

export type Answers = {
  moods: string[]
  runtime: number | null
  era: 'any' | 'new' | 'modern' | 'classic'
  fame: 'any' | 'popular' | 'between' | 'gem'
  source: 'watchlist' | 'mix' | 'discover'
  subtitles: boolean
  animation: boolean
}

export type Service = { name: string; icon: string | null; url: string; kinds: string[] }

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `Request failed (${r.status})`
    try {
      msg = (await r.json()).detail ?? msg
    } catch {
      /* not json */
    }
    throw new Error(msg)
  }
  return r.json()
}

export const api = {
  user: (u: string) => fetch(`/api/user/${encodeURIComponent(u)}`).then(json<Profile>),
  backdrops: () =>
    fetch('/api/backdrops').then(json<{ slug: string; title: string; year: number; backdrop: string }[]>),
  start: (usernames: string[]) =>
    fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usernames }),
    }).then(json<JobState>),
  recommend: (job: string, answers: Answers) =>
    fetch(`/api/jobs/${job}/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers, limit: 120 }),
    }).then(json<Results>),
  vibe: (job: string, moods: string[], era: string) =>
    fetch(`/api/jobs/${job}/vibe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moods, era }),
    }).catch(() => {}),
  availability: (slug: string) =>
    fetch(`/api/film/${slug}/availability`).then(json<{ services: Service[]; country: string | null; unknown?: boolean }>),
  watch(job: string, onState: (s: JobState) => void) {
    const es = new EventSource(`/api/jobs/${job}/events`)
    es.onmessage = (e) => {
      const s: JobState = JSON.parse(e.data)
      onState(s)
      if (s.ready || s.error) es.close()
    }
    return () => es.close()
  },
}

export const fmtRuntime = (m: number | null) => (m ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : '')
