import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Answers, type JobState, type Profile, type Results as R } from './api'
import Landing from './Landing'
import Quiz from './Quiz'
import Results from './Results'
import { Avatar, Icon, Logo } from './ui'

type Stage = 'who' | 'quiz' | 'developing' | 'results'

const DEFAULTS: Answers = { moods: [], runtime: null, era: 'any', fame: 'any', source: 'mix', subtitles: true }

const store = {
  get<T>(k: string, fallback: T): T {
    try {
      return JSON.parse(localStorage.getItem(k) ?? '') ?? fallback
    } catch {
      return fallback
    }
  },
  set(k: string, v: unknown) {
    try {
      localStorage.setItem(k, JSON.stringify(v))
    } catch {
      /* private mode */
    }
  },
}

function Developing({ job, onRetry }: { job: JobState | null; onRetry: () => void }) {
  const [n, setN] = useState(3)
  useEffect(() => {
    const t = setInterval(() => setN((x) => (x === 1 ? 3 : x - 1)), 1000)
    return () => clearInterval(t)
  }, [])
  if (job?.error) {
    return (
      <section className="developing">
        <div className="error-box">
          <span className="eyebrow" style={{ color: 'var(--danger)' }}>Projector jammed</span>
          <h2 className="display" style={{ marginTop: 14 }}>That didn’t work.</h2>
          <p>{job.error}</p>
          <button className="btn primary" onClick={onRetry}>
            <Icon name="restart" /> Try again
          </button>
        </div>
      </section>
    )
  }
  return (
    <section className="developing">
      <div>
        <div className="leader" aria-hidden="true">
          <svg viewBox="0 0 200 200">
            <circle cx="100" cy="100" r="92" fill="none" stroke="var(--line-2)" strokeWidth="1" />
            <circle cx="100" cy="100" r="74" fill="none" stroke="var(--line)" strokeWidth="1" />
            <line x1="100" y1="0" x2="100" y2="200" stroke="var(--line)" />
            <line x1="0" y1="100" x2="200" y2="100" stroke="var(--line)" />
            <motion.circle
              key={n}
              cx="100" cy="100" r="92" fill="none" stroke="var(--accent)" strokeWidth="2"
              strokeDasharray={2 * Math.PI * 92}
              initial={{ strokeDashoffset: 2 * Math.PI * 92 }}
              animate={{ strokeDashoffset: 0 }}
              transition={{ duration: 1, ease: 'linear' }}
              transform="rotate(-90 100 100)"
            />
          </svg>
          <AnimatePresence mode="wait">
            <motion.span key={n} className="count" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.1 }} transition={{ duration: 0.25 }}>
              {n}
            </motion.span>
          </AnimatePresence>
        </div>
        <h2 className="display">Developing your picks</h2>
        <AnimatePresence mode="wait">
          <motion.p key={job?.message} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            {job?.ready ? 'Matching everything to the vibe' : job?.message ?? 'Threading the film'}
          </motion.p>
        </AnimatePresence>
        <div className="bar">
          <div style={{ width: `${Math.max(3, (job?.progress ?? 0) * 100)}%` }} />
        </div>
      </div>
    </section>
  )
}

export default function App() {
  const [stage, setStage] = useState<Stage>('who')
  // storage keys keep the old 'marquee.' prefix so a renamed app still remembers your group
  const [people, setPeople] = useState<Profile[]>(() => store.get('marquee.people', []))
  const [answers, setAnswersState] = useState<Answers>(() => ({ ...DEFAULTS, ...store.get('marquee.answers', {}) }))
  const [job, setJob] = useState<JobState | null>(null)
  const [results, setResults] = useState<R | null>(null)
  const [busy, setBusy] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const stopWatch = useRef<() => void>(() => {})
  const reqId = useRef(0)

  const setAnswers = (a: Answers) => {
    setAnswersState(a)
    store.set('marquee.answers', a)
  }

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [stage])

  const start = async (ps: Profile[], next: Stage = 'quiz') => {
    setPeople(ps)
    store.set('marquee.people', ps)
    setResults(null)
    setJob(null)
    setStage(next)
    stopWatch.current()
    try {
      const j = await api.start(ps.map((p) => p.username))
      setJob(j)
      stopWatch.current = api.watch(j.id, setJob)
    } catch (e) {
      setJob({ id: '', stage: 'error', message: '', progress: 0, error: (e as Error).message, ready: false })
    }
  }

  const fetchPicks = useCallback(
    async (a: Answers) => {
      if (!job?.id) return
      const id = ++reqId.current
      setBusy(true)
      try {
        const r = await api.recommend(job.id, a)
        if (id === reqId.current) {
          setResults(r)
          setStage('results')
        }
      } catch (e) {
        if (id === reqId.current) setJob((j) => (j ? { ...j, error: (e as Error).message } : j))
      } finally {
        if (id === reqId.current) setBusy(false)
      }
    },
    [job?.id],
  )

  // quiz finished: wait for the background job (showing the countdown) then fetch
  useEffect(() => {
    if (stage === 'developing' && job?.ready && !busy) fetchPicks(answers)
  }, [stage, job?.ready]) // eslint-disable-line react-hooks/exhaustive-deps

  // mood + era are known early in the quiz: warm the genre charts for them in the background
  const moodKey = answers.moods.join(',')
  useEffect(() => {
    if (job?.id && moodKey) api.vibe(job.id, answers.moods, answers.era)
  }, [job?.id, moodKey, answers.era]) // eslint-disable-line react-hooks/exhaustive-deps

  // live re-score while tuning
  const retune = (a: Answers) => {
    setAnswers(a)
    fetchPicks(a)
  }

  const reset = () => {
    stopWatch.current()
    setJob(null)
    setResults(null)
    setStage('who')
  }

  return (
    <>
      <div className="grain" aria-hidden="true" />
      <div className="vignette" aria-hidden="true" />
      <header className={`topbar ${scrolled || stage === 'quiz' ? 'solid' : ''}`}>
        <button className="wordmark" onClick={reset} aria-label="Skald, start over">
          <Logo /> Skald
        </button>
        {stage !== 'who' && (
          <div className="topbar-right">
            <span className="avatar-stack hide-sm">
              {people.map((p) => (
                <Avatar key={p.username} p={p} size={30} />
              ))}
            </span>
            {stage === 'results' && (
              <button className="btn small ghost" onClick={() => setStage('quiz')}>
                <Icon name="restart" /> <span className="hide-sm">Retake quiz</span>
              </button>
            )}
            <button className="btn small" onClick={reset}>
              New group
            </button>
          </div>
        )}
      </header>

      <AnimatePresence mode="wait">
        <motion.main key={stage} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.22 }}>
          {stage === 'who' && <Landing initial={people} onStart={start} />}
          {stage === 'quiz' && (
            <Quiz
              people={people}
              answers={answers}
              setAnswers={setAnswers}
              job={job}
              onBack={reset}
              onDone={() => setStage('developing')}
            />
          )}
          {stage === 'developing' && <Developing job={job} onRetry={() => start(people, 'developing')} />}
          {stage === 'results' && results && <Results data={results} answers={answers} onAnswers={retune} busy={busy} />}
        </motion.main>
      </AnimatePresence>
    </>
  )
}
