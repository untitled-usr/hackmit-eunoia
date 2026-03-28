import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  createDriftBottle,
  getDriftBottle,
  pickDriftBottle,
  replyDriftBottle,
  refreshMyDriftBottleCandidates,
  searchDriftBottlesByTag,
  type DriftBottle,
} from '../lib/driftBottlesClient'
import { MidAuthHttpError } from '../lib/midAuth'

const PRESET_TAGS = ['Isolated', 'Stress', 'Loneliness', 'Fatigue', 'Calm'] as const

export function BottlePage() {
  const toastTimerRef = useRef<number | null>(null)

  const [draft, setDraft] = useState('')
  const [selectedPresetTags, setSelectedPresetTags] = useState<string[]>([])
  const [customTagInput, setCustomTagInput] = useState('')
  const [customTags, setCustomTags] = useState<string[]>([])

  const [selectedBottle, setSelectedBottle] = useState<DriftBottle | null>(null)
  const [pickedBottleNames, setPickedBottleNames] = useState<string[]>([])
  const [searchTagInput, setSearchTagInput] = useState('')
  const [searchResults, setSearchResults] = useState<DriftBottle[]>([])
  const [replyDraft, setReplyDraft] = useState('')

  const [toastText, setToastText] = useState<string | null>(null)
  const [throwFeedback, setThrowFeedback] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [isPicking, setIsPicking] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [isReplying, setIsReplying] = useState(false)
  const [remainingPicks, setRemainingPicks] = useState<number | null>(null)

  const showToast = useCallback((message: string, ms = 2200) => {
    setToastText(message)
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current)
    toastTimerRef.current = window.setTimeout(() => {
      setToastText(null)
      toastTimerRef.current = null
    }, ms)
  }, [])

  const readErrorMessage = useCallback((error: unknown) => {
    if (error instanceof MidAuthHttpError) return error.message
    if (error instanceof Error) return error.message
    return 'Request failed, please retry.'
  }, [])

  const mergedTags = useMemo(() => {
    const all = [...selectedPresetTags, ...customTags]
    const uniq = Array.from(new Set(all.map((v) => v.trim()).filter((v) => v.length > 0)))
    return uniq
  }, [selectedPresetTags, customTags])

  const togglePresetTag = useCallback((tag: string) => {
    setSelectedPresetTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    )
  }, [])

  const addCustomTag = useCallback(() => {
    const tag = customTagInput.trim()
    if (!tag) return
    setCustomTags((prev) => {
      if (prev.includes(tag)) return prev
      return [...prev, tag]
    })
    setCustomTagInput('')
  }, [customTagInput])

  const removeTag = useCallback((tag: string) => {
    setCustomTags((prev) => prev.filter((item) => item !== tag))
    setSelectedPresetTags((prev) => prev.filter((item) => item !== tag))
  }, [])

  const onThrowBottle = useCallback(async () => {
    const text = draft.trim()
    if (!text) {
      showToast('Please write down your thoughts first~')
      return
    }
    setIsCreating(true)
    try {
      await createDriftBottle({ content: text, tags: mergedTags })
      setDraft('')
      setSelectedPresetTags([])
      setCustomTags([])
      setThrowFeedback(true)
      showToast('Your drift bottle has entered the sea~')
      window.setTimeout(() => setThrowFeedback(false), 1300)
    } catch (error) {
      showToast(readErrorMessage(error))
    } finally {
      setIsCreating(false)
    }
  }, [draft, mergedTags, readErrorMessage, showToast])

  const onRefreshCandidates = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const result = await refreshMyDriftBottleCandidates()
      showToast(`Candidate pool refreshed: ${result.refreshedCount}`)
    } catch (error) {
      showToast(readErrorMessage(error))
    } finally {
      setIsRefreshing(false)
    }
  }, [readErrorMessage, showToast])

  const onSearchByTag = useCallback(async () => {
    const tag = searchTagInput.trim()
    if (!tag) {
      showToast('Please input a tag first.')
      return
    }
    try {
      const result = await searchDriftBottlesByTag(tag)
      setSearchResults(result.driftBottles)
      showToast(`Found ${result.driftBottles.length} bottles.`)
    } catch (error) {
      showToast(readErrorMessage(error))
    }
  }, [readErrorMessage, searchTagInput, showToast])

  const loadBottleDetail = useCallback(
    async (nameOrId: string) => {
      setIsLoadingDetail(true)
      try {
        const bottle = await getDriftBottle(nameOrId)
        setSelectedBottle(bottle)
        setReplyDraft('')
      } catch (error) {
        showToast(readErrorMessage(error))
      } finally {
        setIsLoadingDetail(false)
      }
    },
    [readErrorMessage, showToast],
  )

  const onOpenDestiny = useCallback(async () => {
    setIsPicking(true)
    try {
      const picked = await pickDriftBottle()
      setRemainingPicks(picked.remainingPicks)
      if (picked.driftBottle.name) {
        setPickedBottleNames((prev) => [picked.driftBottle.name, ...prev.filter((n) => n !== picked.driftBottle.name)])
        await loadBottleDetail(picked.driftBottle.name)
      } else {
        setSelectedBottle(picked.driftBottle)
        setReplyDraft('')
      }
      showToast('A drift bottle reached your hands.')
    } catch (error) {
      showToast(readErrorMessage(error))
    } finally {
      setIsPicking(false)
    }
  }, [loadBottleDetail, readErrorMessage, showToast])

  const onPickAnother = useCallback(() => {
    setSelectedBottle(null)
    setReplyDraft('')
  }, [])

  const onReplyBottle = useCallback(async () => {
    if (!selectedBottle?.name) {
      showToast('Please open a bottle first.')
      return
    }
    const content = replyDraft.trim()
    if (!content) {
      showToast('Please write a reply first.')
      return
    }
    setIsReplying(true)
    try {
      await replyDriftBottle(selectedBottle.name, content)
      setReplyDraft('')
      showToast('Reply sent.')
    } catch (error) {
      showToast(readErrorMessage(error))
    } finally {
      setIsReplying(false)
    }
  }, [readErrorMessage, replyDraft, selectedBottle?.name, showToast])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current)
    }
  }, [])

  return (
    <section id="bottle" className="view page-container active bottle-page">
      <div className="p-6 md:p-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="glass bottle-glass-panel rounded-2xl p-5">
            <h2 className="bottle-title text-2xl font-bold tracking-wide text-slate-800 md:text-3xl">
              Write a Letter to the Ocean
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Entrust your thoughts to the waves, let them carry your worries away...
            </p>

            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={500}
              placeholder="Write something you dare not say..."
              className="mt-4 h-44 w-full rounded-xl border border-slate-200 bg-white/93 p-3 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-sky-300"
            />

            <div className="mt-3">
              <p className="text-xs text-slate-500">Tags</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {PRESET_TAGS.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => togglePresetTag(tag)}
                    className={`rounded-full border px-3 py-1 text-xs transition ${
                      selectedPresetTags.includes(tag)
                        ? 'border-sky-300 bg-sky-100 text-sky-700'
                        : 'border-slate-200 bg-white/92 text-slate-600 hover:bg-white'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
              <div className="mt-2 flex gap-2">
                <input
                  type="text"
                  value={customTagInput}
                  onChange={(e) => setCustomTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addCustomTag()
                    }
                  }}
                  maxLength={32}
                  placeholder="Custom tag..."
                  className="h-9 flex-1 rounded-xl border border-slate-200 bg-white/93 px-3 text-xs outline-none focus:ring-2 focus:ring-sky-300"
                />
                <button type="button" className="btn bottle-btn-glass" onClick={addCustomTag}>
                  Add
                </button>
              </div>
              {mergedTags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {mergedTags.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => removeTag(tag)}
                      className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-600"
                    >
                      {tag} ×
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={onThrowBottle}
              className="btn bottle-btn-glass mt-4 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!draft.trim() || isCreating}
            >
              {isCreating ? 'Sending...' : 'Let Thoughts Drift'}
            </button>

            <p className={`mt-2 text-xs text-sky-700 ${throwFeedback ? '' : 'invisible'}`}>
              Your thoughts are drifting away with the waves
            </p>

            <div className="mt-5 rounded-xl border border-slate-200 bg-white/82 p-3">
              <h3 className="text-sm font-medium text-slate-700">Picked Bottle History</h3>
              <div className="mt-2 max-h-44 space-y-2 overflow-y-auto pr-1">
                {pickedBottleNames.length === 0 ? (
                  <p className="text-xs text-slate-500">No picked bottles yet.</p>
                ) : (
                  pickedBottleNames.map((name) => (
                    <button
                      key={name}
                      type="button"
                      onClick={() => {
                        void loadBottleDetail(name)
                      }}
                      className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      {name}
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="glass bottle-glass-panel rounded-2xl p-5">
            <h2 className="bottle-title text-2xl font-bold tracking-wide text-slate-800 md:text-3xl">
              Ocean&apos;s Gift
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              A wave brings a bottle, waiting for you to open it...
            </p>

            <div className="mt-3">
              <input
                type="text"
                value={searchTagInput}
                onChange={(e) => setSearchTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void onSearchByTag()
                  }
                }}
                placeholder="Search tags..."
                className="h-10 w-full rounded-xl border border-slate-200 bg-white/93 px-3 text-sm outline-none focus:ring-2 focus:ring-sky-300"
              />
              {searchResults.length > 0 && (
                <div className="mt-2 max-h-36 space-y-2 overflow-y-auto rounded-xl border border-slate-200 bg-white/92 p-2">
                  {searchResults.map((item) => (
                    <button
                      key={item.name}
                      type="button"
                      onClick={() => {
                        setSelectedBottle(item)
                        setReplyDraft('')
                      }}
                      className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50"
                    >
                      <div className="truncate font-medium">{item.name}</div>
                      <div className="mt-1 truncate text-[11px] text-slate-500">
                        {item.tags.length > 0 ? item.tags.join(', ') : '(no tags)'}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn bottle-btn-glass"
                onClick={() => {
                  void onRefreshCandidates()
                }}
                disabled={isRefreshing}
              >
                {isRefreshing ? 'Refreshing...' : 'Refresh Candidates'}
              </button>
              <button
                type="button"
                className="btn bottle-btn-glass"
                onClick={() => {
                  void onOpenDestiny()
                }}
                disabled={isPicking}
              >
                {isPicking ? 'Picking...' : 'Open This Destiny'}
              </button>
            </div>
            <p className="mt-2 text-[11px] text-slate-500">
              Remaining picks today:{' '}
              {remainingPicks == null ? '-' : remainingPicks < 0 ? 'Unlimited' : remainingPicks}
            </p>

            {selectedBottle ? (
              <div className="mt-4 rounded-xl border border-slate-200 bg-white/90 p-4">
                <p className="text-xs text-slate-500">You opened a drift bottle...</p>
                <p className="mt-1 text-[11px] text-slate-400">
                  {selectedBottle.name}
                </p>
                <p className="mt-3 whitespace-pre-wrap break-words text-sm text-slate-700">
                  {selectedBottle.content || '(empty content)'}
                </p>
                <p className="mt-2 text-[11px] text-slate-500">
                  Tags: {selectedBottle.tags.length > 0 ? selectedBottle.tags.join(', ') : '(none)'}
                </p>
                <div className="mt-3">
                  <textarea
                    value={replyDraft}
                    onChange={(e) => setReplyDraft(e.target.value)}
                    maxLength={500}
                    placeholder="Reply to this bottle..."
                    className="h-24 w-full rounded-xl border border-slate-200 bg-white/93 p-3 text-xs text-slate-700 outline-none focus:ring-2 focus:ring-sky-300"
                  />
                  <button
                    type="button"
                    className="btn mt-2"
                    onClick={() => {
                      void onReplyBottle()
                    }}
                    disabled={isReplying}
                  >
                    {isReplying ? 'Replying...' : 'Send Reply'}
                  </button>
                </div>

                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs text-slate-700 hover:bg-slate-50"
                    onClick={onPickAnother}
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-white/78 p-6 text-center text-xs text-slate-500">
                {isLoadingDetail ? 'Loading bottle...' : 'Open a bottle to see its message.'}
              </div>
            )}
          </div>
        </div>
      </div>
      <div id="bottle-toast" className={`toast${toastText ? '' : ' hidden'}`} aria-hidden={!toastText}>
        {toastText}
      </div>
    </section>
  )
}
