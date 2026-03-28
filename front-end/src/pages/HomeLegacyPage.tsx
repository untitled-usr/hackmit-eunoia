import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EunoiaDisclaimer } from '../components/EunoiaDisclaimer'
import './home-legacy.css'

const MAIN_TEXT = 'Your mind is a shoreline — where mood shells arrive, stay, and drift away.'
const SEQUENTIAL_LINES = [
  'Enter your shoreline',
  'Talk to the sky — <strong>Personal Agent</strong>',
  'Let it drift — <strong>Drift Bottle</strong>',
  'Leave a trace — <strong>Mood Diary</strong>',
  'Head to the beach and collect your mood shells now!',
]

type Stage = 'initial' | 'sequential' | 'final'
const INTRO_DONE_COOKIE = 'eunoia_frontpage_intro_done'
const INTRO_DONE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365

function hasIntroDoneCookie() {
  if (typeof document === 'undefined') return false
  return document.cookie
    .split(';')
    .map((item) => item.trim())
    .some((item) => item === `${INTRO_DONE_COOKIE}=1`)
}

function setIntroDoneCookie() {
  if (typeof document === 'undefined') return
  document.cookie = `${INTRO_DONE_COOKIE}=1; path=/; max-age=${INTRO_DONE_MAX_AGE_SECONDS}; samesite=lax`
}

function escapeHtml(text: string) {
  return text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
}

function parseStrongSegments(raw: string) {
  const segments: Array<{ text: string; strong: boolean }> = []
  const pattern = /<strong>(.*?)<\/strong>/g
  let lastIndex = 0
  let match = pattern.exec(raw)
  while (match) {
    if (match.index > lastIndex) {
      segments.push({ text: raw.slice(lastIndex, match.index), strong: false })
    }
    segments.push({ text: match[1] ?? '', strong: true })
    lastIndex = pattern.lastIndex
    match = pattern.exec(raw)
  }
  if (lastIndex < raw.length) {
    segments.push({ text: raw.slice(lastIndex), strong: false })
  }
  return segments
}

export function HomeLegacyPage() {
  const initialIntroDoneRef = useRef<boolean>(hasIntroDoneCookie())
  const initialIntroDone = initialIntroDoneRef.current
  const hasAnyCookieRef = useRef<boolean>(
    typeof document !== 'undefined' && document.cookie.trim().length > 0,
  )
  const [stage, setStage] = useState<Stage>(initialIntroDone ? 'final' : 'initial')
  const [introDone, setIntroDone] = useState(initialIntroDone)
  const [isInitialFading, setIsInitialFading] = useState(false)
  const [isBgClear, setIsBgClear] = useState(initialIntroDone)
  const [typingText, setTypingText] = useState('')
  const [lineContents, setLineContents] = useState<string[]>([])
  const [lineVisible, setLineVisible] = useState<boolean[]>([])
  const [showStartButton, setShowStartButton] = useState(false)
  const [startButtonVisible, setStartButtonVisible] = useState(false)

  const isCompleteRef = useRef(false)
  const timeoutIdsRef = useRef<number[]>([])

  const registerTimeout = useCallback((fn: () => void, delay: number) => {
    const id = window.setTimeout(() => {
      timeoutIdsRef.current = timeoutIdsRef.current.filter((item) => item !== id)
      fn()
    }, delay)
    timeoutIdsRef.current.push(id)
    return id
  }, [])

  const wait = useCallback(
    (delay: number) =>
      new Promise<void>((resolve) => {
        registerTimeout(resolve, delay)
      }),
    [registerTimeout],
  )

  const clearAllTimeouts = useCallback(() => {
    for (const id of timeoutIdsRef.current) {
      window.clearTimeout(id)
    }
    timeoutIdsRef.current = []
  }, [])

  const shouldStop = useCallback(() => isCompleteRef.current, [])

  const typePlainText = useCallback(
    async (text: string, speed: number, onChange: (value: string) => void) => {
      let current = ''
      for (const ch of text) {
        if (shouldStop()) return
        current += ch
        onChange(current)
        const jitter = Math.floor(Math.random() * 41) - 20
        await wait(Math.max(16, speed + jitter))
      }
    },
    [shouldStop, wait],
  )

  const typeHtmlLine = useCallback(
    async (line: string, speed: number, onChange: (value: string) => void) => {
      const segments = parseStrongSegments(line)
      let html = ''
      for (const segment of segments) {
        let current = ''
        for (const ch of segment.text) {
          if (shouldStop()) return
          current += ch
          const chunk = segment.strong
            ? `<strong>${escapeHtml(current)}</strong>`
            : escapeHtml(current)
          onChange(html + chunk)
          const jitter = Math.floor(Math.random() * 41) - 20
          await wait(Math.max(16, speed + jitter))
        }
        html += segment.strong
          ? `<strong>${escapeHtml(segment.text)}</strong>`
          : escapeHtml(segment.text)
        onChange(html)
      }
    },
    [shouldStop, wait],
  )

  const completeExperience = useCallback(() => {
    isCompleteRef.current = true
    clearAllTimeouts()
    setIntroDoneCookie()
    setIntroDone(true)
    setIsBgClear(true)
    setShowStartButton(false)
    setStartButtonVisible(false)
    setStage('final')
  }, [clearAllTimeouts])

  const startSequentialTyping = useCallback(async () => {
    if (shouldStop()) return
    setLineContents([])
    setLineVisible([])
    for (const [lineIndex, line] of SEQUENTIAL_LINES.entries()) {
      if (shouldStop()) return
      setLineContents((prev) => [...prev, ''])
      setLineVisible((prev) => [...prev, false])
      await wait(50)
      if (shouldStop()) return
      setLineVisible((prev) => {
        const next = [...prev]
        next[lineIndex] = true
        return next
      })
      await typeHtmlLine(line, 50, (value) => {
        setLineContents((prev) => {
          const next = [...prev]
          next[lineIndex] = value
          return next
        })
      })
      if (shouldStop()) return
      await wait(800)
    }
    if (shouldStop()) return
    setShowStartButton(true)
    await wait(100)
    if (shouldStop()) return
    setStartButtonVisible(true)
  }, [shouldStop, typeHtmlLine, wait])

  const transitionToSequential = useCallback(() => {
    if (shouldStop()) return
    setIsInitialFading(true)
    registerTimeout(() => {
      if (shouldStop()) return
      setStage('sequential')
      void startSequentialTyping()
    }, 1500)
  }, [registerTimeout, shouldStop, startSequentialTyping])

  useEffect(() => {
    if (initialIntroDone || introDone) {
      document.body.classList.remove('home2-intro-active')
      return
    }
    document.body.classList.add('home2-intro-active')
    return () => {
      document.body.classList.remove('home2-intro-active')
    }
  }, [initialIntroDone, introDone])

  useEffect(() => {
    if (initialIntroDone) {
      isCompleteRef.current = true
      clearAllTimeouts()
      return
    }
    isCompleteRef.current = false
    registerTimeout(() => {
      void (async () => {
        if (shouldStop()) return
        await typePlainText(MAIN_TEXT, 70, setTypingText)
        if (shouldStop()) return
        registerTimeout(() => transitionToSequential(), 5000)
      })()
    }, 1000)
    return () => {
      isCompleteRef.current = true
      clearAllTimeouts()
    }
  }, [clearAllTimeouts, initialIntroDone, registerTimeout, shouldStop, transitionToSequential, typePlainText])

  const initialClassName = useMemo(() => {
    const classes = ['glass-container']
    if (stage !== 'initial') classes.push('hidden')
    if (isInitialFading) classes.push('fade-out')
    return classes.join(' ')
  }, [isInitialFading, stage])

  const sequentialClassName = useMemo(() => {
    const classes = ['glass-container']
    if (stage !== 'sequential') classes.push('hidden')
    return classes.join(' ')
  }, [stage])

  const finalClassName = useMemo(() => {
    const classes = ['glass-container']
    if (stage !== 'final') classes.push('hidden')
    return classes.join(' ')
  }, [stage])

  return (
    <section id="home" className={`home2-page${introDone ? '' : ' fullscreen-intro'}`}>
      <div className="background-container">
        <div className={`background-image${isBgClear ? ' clear' : ''}`} />
      </div>
      <main className="content-wrapper">
        <div className={initialClassName}>
          <h1 id="typing-text">
            {typingText}
            {stage === 'initial' ? <span className="cursor" /> : null}
          </h1>
        </div>

        <div className={sequentialClassName}>
          <div id="sequential-lines">
            {lineContents.map((line, index) => (
              <div
                key={`line-${index}`}
                className={`sequential-line${lineVisible[index] ? ' visible' : ''}`}
                dangerouslySetInnerHTML={{
                  __html:
                    line +
                    (stage === 'sequential' && index === lineContents.length - 1 && !showStartButton
                      ? '<span class="cursor"></span>'
                      : ''),
                }}
              />
            ))}
          </div>
          {showStartButton ? (
            <button
              type="button"
              id="start-button"
              className={startButtonVisible ? 'visible' : ''}
              onClick={completeExperience}
            >
              <span className="button-text">Start</span>
            </button>
          ) : null}
        </div>

        <div className={finalClassName}>
          <p className="final-description">
            Eunoia — a quiet shoreline for your mind.
            <br />
            A place where your thoughts can drift like waves,
            <br />
            your feelings can be released into the sea,
            <br />
            and your memories can rest gently on the sand.
            <br />
            You don&apos;t have to fix anything here. Just arrive, stay, and breathe.
          </p>
          <h1 className="floating-text">{MAIN_TEXT}</h1>
        </div>
      </main>

      {hasAnyCookieRef.current ? (
        <button
          type="button"
          id="skip-button"
          className={`scallop-button${stage === 'final' ? ' hidden' : ''}`}
          onClick={completeExperience}
        >
          <span className="button-text">Skip</span>
        </button>
      ) : null}
      <EunoiaDisclaimer />
    </section>
  )
}
