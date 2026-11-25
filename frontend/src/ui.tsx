import { AnimatePresence, motion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import type { Profile } from './api'

const paths = {
  arrow: 'M5 12h14M13 6l6 6-6 6',
  back: 'M19 12H5M11 18l-6-6 6-6',
  play: 'M7 4.5v15l13-7.5z',
  close: 'M6 6l12 12M18 6L6 18',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  bookmark: 'M6 3.5h12v17l-6-4.5-6 4.5z',
  heart: 'M12 20s-7.5-4.6-7.5-10.1C4.5 7 6.6 5 9 5c1.4 0 2.4.6 3 1.6C12.6 5.6 13.6 5 15 5c2.4 0 4.5 2 4.5 4.9C19.5 15.4 12 20 12 20z',
  sparkle: 'M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6zM19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7z',
  shuffle: 'M3 7h3.5c2 0 3.2 1 4.3 2.7l2.4 4.6C14.3 16 15.5 17 17.5 17H21M18 14l3 3-3 3M3 17h3.5c1.3 0 2.2-.4 3-1.2M14.5 8.2c.8-.8 1.7-1.2 3-1.2H21M18 4l3 3-3 3',
  sliders: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5',
  tv: 'M3.5 6.5h17v11h-17zM8 21h8M12 17.5V21',
  restart: 'M4 12a8 8 0 108-8 8.4 8.4 0 00-6 2.5L4 8.5M4 4v4.5h4.5',
}

export function Icon({ name, ...rest }: { name: keyof typeof paths } & React.SVGProps<SVGSVGElement>) {
  const filled = name === 'play' || name === 'sparkle'
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill={filled ? 'currentColor' : 'none'} stroke={filled ? 'none' : 'currentColor'} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" {...rest}>
      <path d={paths[name]} />
    </svg>
  )
}

export function Logo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {/* a round shield carrying the rune ᚦ, whose stave-and-wedge doubles as a play button */}
      <circle cx="12" cy="12" r="8.6" fill="none" stroke="var(--accent)" strokeWidth="1.8" />
      <path d="M9.8 1.8v20.4" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M9.8 8.4 16 12l-6.2 3.6z" fill="var(--accent)" stroke="var(--accent)" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  )
}

export function Avatar({ p, size = 32 }: { p: Pick<Profile, 'avatar' | 'display_name'>; size?: number }) {
  const style = { '--s': `${size}px` } as React.CSSProperties
  return p.avatar ? (
    <img className="avatar" style={style} src={p.avatar} alt="" loading="lazy" />
  ) : (
    <span className="avatar" style={style} aria-hidden="true">
      {p.display_name.slice(0, 1).toUpperCase()}
    </span>
  )
}

export function Overlay({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          {children}
        </>
      )}
    </AnimatePresence>
  )
}

export function TrailerModal({ url, onClose }: { url: string | null; onClose: () => void }) {
  const src = url ? url.replace(/\?.*$/, '') + '?autoplay=1&rel=0&modestbranding=1' : ''
  return (
    <Overlay open={!!url} onClose={onClose}>
      <motion.div className="modal" onClick={onClose} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.98 }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
        <div className="frame" onClick={(e) => e.stopPropagation()}>
          <iframe src={src} title="Trailer" allow="autoplay; encrypted-media; fullscreen" allowFullScreen />
        </div>
        <button className="btn icon close" onClick={onClose} aria-label="Close trailer">
          <Icon name="close" />
        </button>
      </motion.div>
    </Overlay>
  )
}

export function Toast({ text }: { text: string | null }) {
  return (
    <AnimatePresence>
      {text && (
        <motion.div className="toast" role="status" initial={{ opacity: 0, y: 12, x: '-50%' }} animate={{ opacity: 1, y: 0, x: '-50%' }} exit={{ opacity: 0, y: 8, x: '-50%' }}>
          {text}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export const stars = (r: number | null) => (r == null ? '' : r.toFixed(1))
