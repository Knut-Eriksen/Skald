import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { api, type Profile } from './api'
import { Avatar, Icon } from './ui'

type Entry = { key: string; username: string; state: 'pending' | 'ok' | 'error'; profile?: Profile; error?: string }

const ease = [0.22, 1, 0.36, 1] as const

function Backdrops() {
  const [items, setItems] = useState<{ slug: string; title: string; year: number; backdrop: string }[]>([])
  const [i, setI] = useState(0)
  useEffect(() => {
    api.backdrops().then((b) => setItems(b.sort(() => Math.random() - 0.5))).catch(() => {})
  }, [])
  useEffect(() => {
    if (items.length < 2) return
    const t = setInterval(() => setI((x) => (x + 1) % items.length), 7000)
    return () => clearInterval(t)
  }, [items])
  // preload the next one so the crossfade never flashes
  useEffect(() => {
    if (items.length) new Image().src = items[(i + 1) % items.length].backdrop
  }, [i, items])
  const cur = items[i]
  return (
    <>
      <div className="backdrops" aria-hidden="true">
        <AnimatePresence>
          {cur && (
            <motion.img
              key={cur.slug}
              src={cur.backdrop}
              alt=""
              initial={{ opacity: 0, scale: 1.12 }}
              animate={{ opacity: 1, scale: 1.02, transition: { opacity: { duration: 1.8 }, scale: { duration: 9, ease: 'linear' } } }}
              exit={{ opacity: 0, transition: { duration: 1.8 } }}
            />
          )}
        </AnimatePresence>
      </div>
      <AnimatePresence mode="wait">
        {cur && (
          <motion.div className="now-showing" key={cur.slug} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.8, delay: 0.4 }}>
            <div className="eyebrow">Now showing</div>
            <div className="title">
              {cur.title} <span style={{ color: 'var(--faint)' }}>({cur.year})</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

export default function Landing({ initial, onStart }: { initial: Profile[]; onStart: (p: Profile[]) => void }) {
  const [entries, setEntries] = useState<Entry[]>(
    initial.map((p) => ({ key: p.username, username: p.username, state: 'ok', profile: p })),
  )
  const [text, setText] = useState('')
  const [shake, setShake] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    input.current?.focus()
  }, [])

  const add = (raw: string) => {
    const names = raw
      .split(/[\s,]+/)
      .map((s) => s.replace(/^@/, '').replace(/^https?:\/\/(www\.)?letterboxd\.com\//, '').replace(/\/.*$/, '').trim())
      .filter(Boolean)
    const taken = new Set(entries.map((e) => e.username.toLowerCase()))
    for (const name of names) {
      if (taken.has(name.toLowerCase())) continue
      if (taken.size >= 8) break
      taken.add(name.toLowerCase())
      const key = name + Date.now()
      setEntries((es) => [...es, { key, username: name, state: 'pending' }])
      api
        .user(name)
        .then((p) => setEntries((es) => es.map((e) => (e.key === key ? { ...e, state: 'ok', profile: p } : e))))
        .catch((err: Error) => {
          setEntries((es) => es.map((e) => (e.key === key ? { ...e, state: 'error', error: err.message } : e)))
          setShake((s) => s + 1)
        })
    }
    setText('')
  }

  const remove = (key: string) => setEntries((es) => es.filter((e) => e.key !== key))
  const ok = entries.filter((e) => e.state === 'ok')
  const pending = entries.some((e) => e.state === 'pending')
  const canGo = ok.length > 0 && !pending
  const go = () => canGo && onStart(ok.map((e) => e.profile!))

  return (
    <section className="landing">
      <Backdrops />
      <div className="landing-inner">
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, ease }}>
          <span className="eyebrow accent">Movie night, solved</span>
          <h1 className="display">
            The film <em>everyone</em>
            <br />
            wants to watch.
          </h1>
          <p className="lede">
            Add your Letterboxd usernames and answer a few quick questions. Marquee reads every diary entry, like and watchlist, then
            picks tonight's film for the whole room.
          </p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, delay: 0.15, ease }}>
          <motion.div className="who-box" key={shake} animate={shake ? { x: [0, -8, 8, -5, 5, 0] } : {}} transition={{ duration: 0.4 }}>
            <div className="chips">
              <AnimatePresence initial={false}>
                {entries.map((e) => (
                  <motion.span
                    key={e.key}
                    layout
                    className={`chip ${e.state === 'pending' ? 'pending' : ''} ${e.state === 'error' ? 'error' : ''}`}
                    initial={{ opacity: 0, scale: 0.85 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.85 }}
                    transition={{ duration: 0.25, ease }}
                    title={e.error}
                  >
                    {e.state === 'ok' && e.profile && <Avatar p={e.profile} />}
                    {e.state === 'pending' && <span className="spin" />}
                    <span>{e.profile?.display_name ?? e.username}</span>
                    {e.state === 'ok' && e.profile && <span className="meta">{e.profile.films_count.toLocaleString()} films</span>}
                    {e.state === 'error' && <span className="meta" style={{ color: 'inherit' }}>not found</span>}
                    <button onClick={() => remove(e.key)} aria-label={`Remove ${e.username}`}>
                      <Icon name="close" width={14} height={14} />
                    </button>
                  </motion.span>
                ))}
              </AnimatePresence>
            </div>
            <div className="who-row">
              <span className="at">@</span>
              <input
                ref={input}
                className="who-input"
                value={text}
                placeholder={entries.length ? 'Add someone else…' : 'Letterboxd username'}
                aria-label="Letterboxd username"
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                onChange={(e) => {
                  const v = e.target.value
                  if (/[\s,]$/.test(v)) add(v)
                  else setText(v)
                }}
                onPaste={(e) => {
                  const v = e.clipboardData.getData('text')
                  if (/[\s,]/.test(v.trim())) {
                    e.preventDefault()
                    add(v)
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    if (text.trim()) add(text)
                    else go()
                  } else if (e.key === 'Backspace' && !text && entries.length) {
                    remove(entries[entries.length - 1].key)
                  }
                }}
              />
              <button className="btn primary" disabled={!canGo && !text.trim()} onClick={() => (text.trim() ? add(text) : go())}>
                {text.trim() ? 'Add' : ok.length > 1 ? `Continue with ${ok.length}` : 'Continue'}
                <Icon name="arrow" />
              </button>
            </div>
          </motion.div>
          <div className="who-foot">
            <span className="hint">
              <span className="kbd">Enter</span> to add · <b>Solo works too</b>. Up to 8 people, public profiles only.
            </span>
          </div>
        </motion.div>

        <motion.div className="how" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1, delay: 0.5 }}>
          <div>
            <span>01 — Read</span>Every diary entry, rating, like and watchlist, so nobody gets something they've already seen.
          </div>
          <div>
            <span>02 — Ask</span>Six quick taps on mood, time and era while we do the reading in the background.
          </div>
          <div>
            <span>03 — Pick</span>A top pick for the whole group, with the reasons behind it, a trailer and where to stream it.
          </div>
        </motion.div>
      </div>
    </section>
  )
}
