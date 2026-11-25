import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useState } from 'react'
import type { Answers, JobState, Profile } from './api'
import { Avatar, Icon } from './ui'

type Opt = { v: unknown; label: string; sub: string; glow?: string }
export type Step = { key: keyof Answers; eyebrow: string; q: string; hint?: string; multi?: number; options: Opt[] }

export const MOODS: Opt[] = [
  { v: 'cozy', label: 'Cozy', sub: 'Warm, feel-good, easy', glow: '#e8a33d' },
  { v: 'tense', label: 'Thrilling', sub: 'Suspense, crime, spies', glow: '#d2452f' },
  { v: 'funny', label: 'Funny', sub: 'Comedies', glow: '#e9d14a' },
  { v: 'emotional', label: 'Emotional', sub: 'Moving dramas, a good cry', glow: '#4f79b8' },
  { v: 'mindbend', label: 'Mind-bending', sub: 'Twists and big ideas', glow: '#8a63e0' },
  { v: 'dark', label: 'Scary', sub: 'Horror and creepy stuff', glow: '#8f1f1f' },
  { v: 'epic', label: 'Epic adventure', sub: 'Big, sweeping, long', glow: '#e07b2c' },
  { v: 'romantic', label: 'Romantic', sub: 'Love stories', glow: '#dc5f83' },
  { v: 'artful', label: 'Artsy', sub: 'Slow, beautiful, arthouse', glow: '#3da393' },
  { v: 'true', label: 'True story', sub: 'Real events and documentaries', glow: '#9b9488' },
]

export function steps(solo: boolean): Step[] {
  return [
    { key: 'moods', eyebrow: 'The mood', q: "What's the mood tonight?", hint: 'Pick one or two. Skip to keep it open.', multi: 2, options: MOODS },
    {
      key: 'runtime', eyebrow: 'The clock', q: 'How much time have you got?',
      options: [
        { v: 100, label: 'A quick one', sub: 'Under 1h 40m' },
        { v: 130, label: 'A regular evening', sub: 'Up to 2h 10m' },
        { v: 160, label: 'Settle in', sub: 'Up to 2h 40m' },
        { v: null, label: 'All night', sub: 'No limit' },
      ],
    },
    {
      key: 'era', eyebrow: 'The era', q: 'Any era you’re craving?',
      options: [
        { v: 'new', label: 'Fresh', sub: '2015 to now' },
        { v: 'modern', label: 'Modern classics', sub: '1990 – 2014' },
        { v: 'classic', label: 'Golden oldies', sub: 'Before 1990' },
        { v: 'any', label: 'Surprise me', sub: 'Any decade goes' },
      ],
    },
    {
      key: 'fame', eyebrow: 'The reputation', q: 'Crowd-pleaser or hidden gem?',
      options: [
        { v: 'popular', label: 'Crowd-pleaser', sub: 'Everyone’s seen it, except you' },
        { v: 'between', label: 'In between', sub: 'Known, not overplayed' },
        { v: 'gem', label: 'Hidden gem', sub: 'Deep cuts and discoveries' },
        { v: 'any', label: 'Don’t mind', sub: 'Just make it good' },
      ],
    },
    {
      key: 'source', eyebrow: 'The shelf', q: 'Where should we look?',
      options: [
        { v: 'watchlist', label: solo ? 'My watchlist' : 'Our watchlists', sub: 'Finally get to those' },
        { v: 'mix', label: 'Mix it up', sub: 'Watchlists plus new finds' },
        { v: 'discover', label: 'Something new', sub: solo ? 'Nothing I’ve listed yet' : 'Nothing anyone has listed' },
      ],
    },
    {
      key: 'subtitles', eyebrow: 'The fine print', q: 'Subtitles tonight?',
      options: [
        { v: true, label: 'Bring them on', sub: 'Any language' },
        { v: false, label: 'English only', sub: 'Keep it easy' },
      ],
    },
  ]
}

const ease = [0.22, 1, 0.36, 1] as const

export default function Quiz({
  people, answers, setAnswers, job, onDone, onBack,
}: {
  people: Profile[]
  answers: Answers
  setAnswers: (a: Answers) => void
  job: JobState | null
  onDone: () => void
  onBack: () => void
}) {
  // ponytail: the quiz asks only mood + time; era, fame, shelf and subtitles keep defaults and live in the tune drawer
  const all = steps(people.length === 1).slice(0, 2)
  const [i, setI] = useState(0)
  const [dir, setDir] = useState(1)
  const step = all[i]
  const value = answers[step.key]

  const next = useCallback(() => {
    if (i === all.length - 1) return onDone()
    setDir(1)
    setI(i + 1)
  }, [i, all.length, onDone])
  const prev = useCallback(() => {
    if (i === 0) return onBack()
    setDir(-1)
    setI(i - 1)
  }, [i, onBack])

  const choose = useCallback(
    (o: Opt) => {
      if (step.multi) {
        const cur = value as string[]
        const v = o.v as string
        const nextVal = cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v].slice(-step.multi)
        setAnswers({ ...answers, [step.key]: nextVal })
      } else {
        setAnswers({ ...answers, [step.key]: o.v })
        setTimeout(next, 260)
      }
    },
    [step, value, answers, setAnswers, next],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const n = e.key === '0' ? 10 : Number(e.key)
      if (n >= 1 && n <= step.options.length) choose(step.options[n - 1])
      else if (e.key === 'Enter') next()
      else if (e.key === 'Backspace' || e.key === 'ArrowLeft') prev()
      else if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, choose, next, prev])

  const selected = (o: Opt) => (step.multi ? (value as string[]).includes(o.v as string) : value === o.v)

  return (
    <>
      <div className="quiz-progress">
        <div style={{ width: `${((i + 1) / all.length) * 100}%` }} />
      </div>
      <section className="quiz">
        <AnimatePresence mode="wait" custom={dir}>
          <motion.div
            key={step.key}
            custom={dir}
            initial={{ opacity: 0, x: dir * 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: dir * -40 }}
            transition={{ duration: 0.45, ease }}
          >
            <div className="quiz-head">
              <span className="eyebrow accent">
                {String(i + 1).padStart(2, '0')} / {String(all.length).padStart(2, '0')} — {step.eyebrow}
              </span>
              <h2 className="display">{step.q}</h2>
              {step.hint && <p>{step.hint}</p>}
            </div>
            <div className={`options ${step.key === 'moods' ? 'moods' : ''}`}>
              {step.options.map((o, n) => (
                <motion.button
                  key={String(o.v)}
                  className={`option ${step.key !== 'moods' ? 'wide' : ''}`}
                  aria-pressed={selected(o)}
                  style={o.glow ? ({ '--glow': o.glow } as React.CSSProperties) : undefined}
                  onClick={() => choose(o)}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.04 * n, ease }}
                >
                  <span className="num">
                    {String(n + 1).padStart(2, '0')}
                    <span className="check">{selected(o) && <Icon name="check" width={12} height={12} strokeWidth={2.5} />}</span>
                  </span>
                  <span>
                    <div className="label">{o.label}</div>
                    <div className="sub">{o.sub}</div>
                  </span>
                </motion.button>
              ))}
            </div>
          </motion.div>
        </AnimatePresence>
      </section>
      <footer className="quiz-foot">
        <div className="loading-line" aria-live="polite">
          <span className="avatar-stack">
            {people.slice(0, 4).map((p) => (
              <Avatar key={p.username} p={p} size={26} />
            ))}
          </span>
          {job && !job.ready && !job.error && (
            <>
              <span className="mini-bar">
                <div style={{ width: `${Math.max(4, job.progress * 100)}%` }} />
              </span>
              <span className="msg">{job.message}</span>
            </>
          )}
          {job?.ready && <span className="msg">All diaries read. Your picks are ready.</span>}
          {job?.error && <span className="msg" style={{ color: 'var(--danger)' }}>{job.error}</span>}
        </div>
        <div className="quiz-actions">
          <button className="btn ghost" onClick={prev}>
            <Icon name="back" /> <span className="hide-sm">Back</span>
          </button>
          <button className="btn primary" onClick={next}>
            {i === all.length - 1 ? 'Show my film' : step.multi && !(value as string[]).length ? 'Skip' : 'Next'}
            <Icon name="arrow" />
          </button>
        </div>
      </footer>
    </>
  )
}
