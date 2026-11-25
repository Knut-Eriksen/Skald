import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'
import { api, fmtRuntime, type Answers, type Film, type Member, type Pick, type Results as R, type Service } from './api'
import { steps } from './Quiz'
import { Avatar, Icon, Overlay, stars, Toast, TrailerModal } from './ui'

const ease = [0.23, 1, 0.32, 1] as const
const drawerEase = [0.32, 0.72, 0, 1] as const
const reasonIcon = { watchlist: 'bookmark', taste: 'heart', vibe: 'sparkle' } as const

function Poster({ film, eager }: { film: Film; eager?: boolean }) {
  const [broken, setBroken] = useState(false)
  return film.poster && !broken ? (
    <img src={film.poster} alt={`${film.title} poster`} loading={eager ? 'eager' : 'lazy'} onError={() => setBroken(true)} />
  ) : (
    <div className="no-poster">{film.title}</div>
  )
}

function WhereToWatch({ slug }: { slug: string }) {
  const [data, setData] = useState<{ services: Service[]; country: string | null } | null>(null)
  useEffect(() => {
    let live = true
    setData(null)
    api.availability(slug).then((d) => live && setData(d)).catch(() => live && setData({ services: [], country: null }))
    return () => {
      live = false
    }
  }, [slug])
  if (!data) return <div className="services"><span className="spin" /></div>
  if (!data.services.length) return null
  const order = (s: Service) => (s.kinds.includes('stream') || s.kinds.includes('free') ? 0 : 1)
  return (
    <motion.div className="services" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <span className="eyebrow">Watch{data.country ? ` in ${data.country}` : ''}</span>
      {[...data.services].sort((a, b) => order(a) - order(b)).slice(0, 6).map((s) => (
        <a key={s.name} className="service" href={s.url} target="_blank" rel="noreferrer noopener">
          {s.icon && <img src={s.icon} alt="" />}
          {s.name}
          <span className="kind">{s.kinds.includes('stream') ? 'Stream' : s.kinds.includes('free') ? 'Free' : s.kinds.includes('rent') ? 'Rent' : s.kinds[0] ?? ''}</span>
        </a>
      ))}
    </motion.div>
  )
}

function Hero({ pick, members, onTrailer, onSkip, skipLabel }: { pick: Pick; members: Member[]; onTrailer: () => void; onSkip: () => void; skipLabel: string }) {
  const f = pick.film
  const byName = Object.fromEntries(members.map((m) => [m.username, m]))
  const solo = members.length === 1
  return (
    <section className="hero">
      <AnimatePresence>
        <motion.div
          key={f.slug}
          className={`hero-bg ${f.backdrop ? '' : 'poster-fallback'}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.6 }}
        >
          {(f.backdrop || f.poster) && (
            <motion.img
              src={f.backdrop || f.poster!}
              alt=""
              initial={{ scale: 1.08 }}
              animate={{ scale: 1 }}
              transition={{ duration: 12, ease: 'linear' }}
            />
          )}
        </motion.div>
      </AnimatePresence>

      <AnimatePresence mode="wait">
        <motion.div
          key={f.slug}
          className="hero-grid"
          initial="hidden"
          animate="show"
          exit="exit"
          variants={{ hidden: {}, show: { transition: { staggerChildren: 0.04 } }, exit: { opacity: 0, transition: { duration: 0.15 } } }}
        >
          <div className="hero-copy">
            {(['eyebrow', 'title', 'meta', 'tagline', 'syn', 'reasons', 'actions'] as const).map((part) => (
              <motion.div key={part} variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.32, ease } } }}>
                {part === 'eyebrow' && <span className="eyebrow accent">{skipLabel}</span>}
                {part === 'title' && <h1 className="display hero-title">{f.title}</h1>}
                {part === 'meta' && (
                  <div className="meta-row">
                    {f.year && <b>{f.year}</b>}
                    {f.directors[0] && (<><span className="dot" /><span>Directed by <b>{f.directors.slice(0, 2).join(' & ')}</b></span></>)}
                    {f.runtime && (<><span className="dot" /><span>{fmtRuntime(f.runtime)}</span></>)}
                    {f.rating && (<><span className="dot" /><span><span className="star">★</span> <b>{stars(f.rating)}</b> on Letterboxd</span></>)}
                    {f.genres.length > 0 && (<><span className="dot" /><span>{f.genres.slice(0, 3).join(', ')}</span></>)}
                  </div>
                )}
                {part === 'tagline' && f.tagline && <p className="tagline">{f.tagline}</p>}
                {part === 'syn' && f.synopsis && <p className="synopsis">{f.synopsis}</p>}
                {part === 'reasons' && pick.reasons.length > 0 && (
                  <ul className="reasons">
                    {pick.reasons.map((r) => (
                      <li key={r.text}>
                        <Icon name={reasonIcon[r.kind]} />
                        {r.text}
                      </li>
                    ))}
                  </ul>
                )}
                {part === 'actions' && (
                  <>
                    <div className="hero-actions">
                      {f.trailer && (
                        <button className="btn primary" onClick={onTrailer}>
                          <Icon name="play" /> Play trailer
                        </button>
                      )}
                      <a className="btn" href={`https://letterboxd.com/film/${f.slug}/`} target="_blank" rel="noreferrer noopener">
                        Letterboxd <Icon name="external" />
                      </a>
                      <button className="btn ghost" onClick={onSkip}>
                        <Icon name="shuffle" /> Not tonight
                      </button>
                    </div>
                    <WhereToWatch slug={f.slug} />
                  </>
                )}
              </motion.div>
            ))}
          </div>

          <motion.aside className="hero-side" variants={{ hidden: { opacity: 0, y: 12, scale: 0.98 }, show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.4, ease } } }}>
            <div className="poster">
              <Poster film={f} eager />
            </div>
            <div className="matchcard">
              <div className="big">
                <span className="eyebrow">{solo ? 'Taste match' : 'Group taste match'}</span>
                <strong>{pick.match}%</strong>
              </div>
              {!solo &&
                pick.members.map((m) => {
                  const p = byName[m.username]
                  return (
                    <div className="member-row" key={m.username}>
                      {p && <Avatar p={p} size={24} />}
                      <span className="name">{p?.display_name ?? m.username}</span>
                      {m.watchlisted && <Icon name="bookmark" className="bm" aria-label="On their watchlist" />}
                      <span className="meter"><div style={{ width: `${m.match}%` }} /></span>
                      <span className="pct">{m.match}</span>
                    </div>
                  )
                })}
              {solo && <div className="member-row" style={{ borderTop: 0, color: 'var(--muted)' }}>{pick.source === 'watchlist' ? 'From your watchlist' : 'A new find for you'}</div>}
            </div>
          </motion.aside>
        </motion.div>
      </AnimatePresence>
    </section>
  )
}

function Card({ pick, onClick, i, rank }: { pick: Pick; onClick: () => void; i: number; rank: number }) {
  const f = pick.film
  return (
    <motion.button
      className="card"
      onClick={onClick}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(i, 10) * 0.025, ease }}
    >
      <div className="poster">
        <Poster film={f} />
        <span className="badge" title={`${pick.match}% taste match`}>#{rank}</span>
        <span className="src" title={pick.source === 'watchlist' ? 'On a watchlist' : 'New find'}>
          <Icon name={pick.source === 'watchlist' ? 'bookmark' : 'sparkle'} />
        </span>
        <div className="overlay">
          {pick.reasons.slice(0, 2).map((r) => (
            <div key={r.text}>{r.text}</div>
          ))}
        </div>
      </div>
      <div>
        <div className="t">{f.title}</div>
        <div className="s">
          {[f.year, fmtRuntime(f.runtime), f.rating ? `★ ${stars(f.rating)}` : null].filter(Boolean).join('  ·  ')}
        </div>
      </div>
    </motion.button>
  )
}

function Tune({ open, onClose, answers, onChange }: { open: boolean; onClose: () => void; answers: Answers; onChange: (a: Answers) => void }) {
  return (
    <Overlay open={open} onClose={onClose}>
      <motion.aside className="drawer" initial={{ x: '100%' }} animate={{ x: 0, transition: { duration: 0.4, ease: drawerEase } }} exit={{ x: '100%', transition: { duration: 0.25, ease: drawerEase } }} aria-label="Adjust the vibe">
        <header>
          <h3 className="display">Adjust the vibe</h3>
          <button className="btn icon small ghost" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </header>
        <div className="body">
          {steps().map((s) => (
            <section key={s.key}>
              <span className="eyebrow">{s.eyebrow}</span>
              <div className="pills">
                {s.options.map((o) => {
                  const cur = answers[s.key]
                  const on = s.multi ? (cur as string[]).includes(o.v as string) : cur === o.v
                  return (
                    <button
                      key={String(o.v)}
                      className="pill"
                      aria-pressed={on}
                      onClick={() => {
                        if (s.multi) {
                          const arr = cur as string[]
                          const v = o.v as string
                          onChange({ ...answers, [s.key]: on ? arr.filter((x) => x !== v) : [...arr, v].slice(-s.multi) })
                        } else onChange({ ...answers, [s.key]: o.v })
                      }}
                    >
                      {o.label}
                    </button>
                  )
                })}
              </div>
            </section>
          ))}
        </div>
        <footer>
          <span>Picks update as you tap.</span>
          <button className="btn small primary" onClick={onClose}>Done</button>
        </footer>
      </motion.aside>
    </Overlay>
  )
}

type Filter = 'all' | 'watchlist' | 'discovery'

export default function Results({ data, answers, onAnswers, busy }: { data: R; answers: Answers; onAnswers: (a: Answers) => void; busy: boolean }) {
  const [skipped, setSkipped] = useState<string[]>([])
  const [chosen, setChosen] = useState<string | null>(null)
  const [trailer, setTrailer] = useState<string | null>(null)
  const [tune, setTune] = useState(false)
  const [filter, setFilter] = useState<Filter>('all')
  const [streamOnly, setStreamOnly] = useState(false)
  const [streamable, setStreamable] = useState<Record<string, boolean>>({})
  const [checking, setChecking] = useState(false)

  // "Streaming now": look up availability for every pick (cached server-side for a day)
  useEffect(() => {
    if (!streamOnly) return
    const todo = data.picks.map((p) => p.film.slug).filter((s) => !(s in streamable))
    if (!todo.length) return
    let live = true
    setChecking(true)
    Promise.all(
      todo.map((s) =>
        api.availability(s).then(
          (a) => [s, !!a.unknown || a.services.some((x) => x.kinds.includes('stream') || x.kinds.includes('free'))] as const, // couldn't check: keep it
          () => [s, false] as const,
        ),
      ),
    ).then((rows) => {
      if (!live) return
      setStreamable((m) => ({ ...m, ...Object.fromEntries(rows) }))
      setChecking(false)
    })
    return () => {
      live = false
    }
  }, [streamOnly, data]) // eslint-disable-line react-hooks/exhaustive-deps
  const [toast, setToast] = useState<string | null>(null)
  const [pastHero, setPastHero] = useState(false)
  useEffect(() => {
    const onScroll = () => setPastHero(window.scrollY > window.innerHeight * 0.6)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  const solo = data.members.length === 1

  // new results (re-tuned vibe) reset the hero
  useEffect(() => {
    setSkipped([])
    setChosen(null)
  }, [data])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 2200)
    return () => clearTimeout(t)
  }, [toast])

  const available = data.picks.filter(
    (p) => !skipped.includes(p.film.slug) && (!streamOnly || checking || streamable[p.film.slug]),
  )
  const hero = (chosen && data.picks.find((p) => p.film.slug === chosen)) || available[0]
  const rest = useMemo(
    () => available.filter((p) => p !== hero && (filter === 'all' || p.source === filter)),
    [available, hero, filter],
  )
  const rank = hero ? data.picks.indexOf(hero) : 0

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || trailer || tune) return
      if (e.key === 't' && hero?.film.trailer) setTrailer(hero.film.trailer)
      if (e.key === 'n') skip()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const skip = () => {
    if (!hero) return
    setSkipped((s) => [...s, hero.film.slug])
    setChosen(null)
    setToast(`Skipped ${hero.film.title}`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (!hero) {
    return (
      <section className="more" style={{ paddingTop: 160 }}>
        <div className="empty">
          <h3 className="display">{streamOnly ? 'None of these are streaming here.' : 'Nothing fits that exact vibe.'}</h3>
          <p>
            {streamOnly
              ? 'They’re all rent-or-buy where you are. Show everything, or loosen the vibe for more options.'
              : 'Loosen a filter (runtime, era or subtitles usually does it) and the picks come straight back.'}
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 20 }}>
            {streamOnly && (
              <button className="btn" onClick={() => setStreamOnly(false)}>
                Show everything
              </button>
            )}
            <button className="btn primary" onClick={() => setTune(true)}>
              <Icon name="sliders" /> Adjust the vibe
            </button>
          </div>
        </div>
        <Tune open={tune} onClose={() => setTune(false)} answers={answers} onChange={onAnswers} />
      </section>
    )
  }

  const label = rank === 0 ? (solo ? 'Your film tonight' : 'Tonight’s pick for all of you') : chosen ? `Pick #${rank + 1}` : 'Next up'

  return (
    <>
      <Hero pick={hero} members={data.members} onTrailer={() => setTrailer(hero.film.trailer)} onSkip={skip} skipLabel={label} />

      <section className="more">
        <div className="more-head">
          <div>
            <span className="eyebrow">Also worth a look{busy && ' · updating…'}</span>
            <h3 className="display">{rest.length} more for {solo ? 'you' : 'the group'}</h3>
          </div>
          <div className="filters">
            {(['all', 'watchlist', 'discovery'] as Filter[]).map((f) => (
              <button key={f} className="seg" aria-pressed={filter === f} onClick={() => setFilter(f)}>
                {{ all: 'Everything', watchlist: solo ? 'My watchlist' : 'Watchlists', discovery: 'New finds' }[f]}
              </button>
            ))}
            <button className="seg" aria-pressed={streamOnly} onClick={() => setStreamOnly((v) => !v)}>
              {checking ? 'Checking services…' : 'Streaming now'}
            </button>
            <button className="seg" onClick={() => setTune(true)}>
              Adjust the vibe
            </button>
          </div>
        </div>
        {/* no layout animation: 120 cards animating layout on the main thread janks every filter toggle */}
        <div className="grid" style={{ opacity: busy ? 0.5 : 1, transition: 'opacity 200ms ease' }}>
            {rest.map((p, i) => (
              <Card
                key={p.film.slug}
                pick={p}
                i={i}
                rank={data.picks.indexOf(p) + 1}
                onClick={() => {
                  setChosen(p.film.slug)
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
              />
            ))}
        </div>
        {rest.length === 0 && <div className="empty">Nothing in this shelf with the current vibe.</div>}
        <p className="stats-line" style={{ marginTop: 56 }}>
          Weighed {data.stats.considered.toLocaleString()} films · {data.stats.watchlisted.toLocaleString()} from watchlists ·{' '}
          {data.stats.discovered.toLocaleString()} found through {solo ? 'your' : 'everyone’s'} favourites · Shortcuts:{' '}
          <span className="kbd">T</span> trailer <span className="kbd">N</span> not tonight
        </p>
      </section>

      <TrailerModal url={trailer} onClose={() => setTrailer(null)} />
      <Tune open={tune} onClose={() => setTune(false)} answers={answers} onChange={onAnswers} />
      <Toast text={toast} />
      <AnimatePresence>
        {pastHero && (
          <motion.button className="btn fab" onClick={() => setTune(true)} initial={{ opacity: 0, y: 16, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.96 }} transition={{ duration: 0.22, ease }}>
            <Icon name="sliders" /> Adjust the vibe
          </motion.button>
        )}
      </AnimatePresence>
    </>
  )
}
