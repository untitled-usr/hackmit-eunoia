import { type ChangeEvent, type MouseEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../context/useAuth'
import { fetchDiaryEntriesFromMemos, saveDiaryEntriesToMemos } from '../lib/midAuthDiary'
import './diary.css'

type ViewMode = 'unlocked' | 'locked' | 'bookshelf'
type EntryStatus = 'digested' | 'archived'
type Mood = '😊' | '😢' | '😠' | '😮' | '😍'
type LockDuration = 'none' | 'minute' | 'week' | 'month'
type StickerKind = 'emoji' | 'text' | 'image'

type StickerItem = {
  id: number
  kind: StickerKind
  content: string
  xPercent: number
  yPercent: number
  scale: number
  rotation: number
}

type DiaryEntry = {
  id: number
  title: string
  text: string
  mood: Mood
  moodIntensity: number
  keywords: string[]
  timestamp: string
  locked: boolean
  unlockTime: string | null
  unlockedAt?: string | null
  status?: EntryStatus
  stickers?: StickerItem[]
}

const MOODS: Mood[] = ['😊', '😢', '😠', '😮', '😍']
const STICKER_EMOJIS = ['🎨', '📓', '💡', '❤️', '⭐']
const STICKER_TEXTS = ['Happy', 'Blessed', 'Grateful', 'Peaceful']
const PROMPTS = [
  'What did I regret today?',
  'What stayed with me the longest?',
  'What did I avoid?',
  'What made me feel strongly?',
  'What small detail mattered?',
  'Did I treat myself kindly?',
  'What am I still processing?',
  'What would I tell myself honestly?',
  'What made me smile unexpectedly today?',
  'What is one thing I learned about myself recently?',
  'What was the most challenging part of my day?',
  'If I could relive one moment from today, which would it be?',
  'What am I grateful for right now?',
  'Who made a difference in my day?',
  'What is a goal I want to set for tomorrow?',
  'How did I handle stress today?',
  'What is a song that describes my mood right now?',
  'What would I say to my younger self today?',
  'What is a habit I want to cultivate?',
  'What made me feel proud today?',
  'What is a fear I faced or need to face?',
  'How did I show love or kindness today?',
  'What is a dream I had recently?',
  'What does "peace" feel like to me today?',
  'What is one thing I want to let go of?',
  'What made me feel energized today?',
  'What is a book or movie that resonated with me lately?',
  'What is a place where I feel most at home?',
  'What is a quality I admire in someone else?',
  'What is a memory that popped up today?',
  'What would I do if I had no fear for one day?',
  'What is a question I have for the universe?',
  'How do I want to be remembered today?',
  'What is a simple pleasure I enjoyed today?',
  'What is a boundary I set or need to set?',
]

type StickerPointer = {
  entryId: number
  stickerId: number
}

type DraggingSticker = {
  entryId: number
  stickerId: number
  rect: DOMRect
}

type StickerTransformMode = 'rotate' | 'scale'

type TransformingSticker = {
  entryId: number
  stickerId: number
  mode: StickerTransformMode
  centerX: number
  centerY: number
  startAngle: number
  startRotation: number
  startDistance: number
  startScale: number
  startUnitX: number
  startUnitY: number
}

type CropBox = {
  x: number
  y: number
  size: number
}

type CropViewport = {
  scale: number
  offsetX: number
  offsetY: number
}

const STICKER_MIN_SCALE = 0.5
const STICKER_MAX_SCALE = 2.5

function ScratchRevealOverlay() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !canvas.parentElement) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let drawing = false

    const paintMask = () => {
      canvas.width = canvas.parentElement?.clientWidth ?? 0
      canvas.height = canvas.parentElement?.clientHeight ?? 0
      ctx.globalCompositeOperation = 'source-over'
      ctx.fillStyle = '#e0e0e0'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.globalCompositeOperation = 'destination-out'
    }

    paintMask()
    const onResize = () => paintMask()
    window.addEventListener('resize', onResize)

    const scratchAt = (clientX: number, clientY: number) => {
      const rect = canvas.getBoundingClientRect()
      ctx.beginPath()
      ctx.arc(clientX - rect.left, clientY - rect.top, 20, 0, Math.PI * 2)
      ctx.fill()
    }

    const onMouseDown = () => {
      drawing = true
    }
    const onMouseUp = () => {
      drawing = false
    }
    const onMouseMove = (event: globalThis.MouseEvent) => {
      if (!drawing) return
      scratchAt(event.clientX, event.clientY)
    }

    const onTouchStart = () => {
      drawing = true
    }
    const onTouchEnd = () => {
      drawing = false
    }
    const onTouchMove = (event: TouchEvent) => {
      if (!drawing) return
      const touch = event.touches[0]
      if (!touch) return
      scratchAt(touch.clientX, touch.clientY)
    }

    canvas.addEventListener('mousedown', onMouseDown)
    window.addEventListener('mouseup', onMouseUp)
    canvas.addEventListener('mousemove', onMouseMove)
    canvas.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchend', onTouchEnd)
    canvas.addEventListener('touchmove', onTouchMove, { passive: true })

    return () => {
      window.removeEventListener('resize', onResize)
      canvas.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('mouseup', onMouseUp)
      canvas.removeEventListener('mousemove', onMouseMove)
      canvas.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchend', onTouchEnd)
      canvas.removeEventListener('touchmove', onTouchMove)
    }
  }, [])

  return <canvas className="diary-scratch-canvas" />
}

function calculateUnlockTime(lockDuration: LockDuration): string | null {
  if (lockDuration === 'none') return null
  const unlockAt = new Date()
  if (lockDuration === 'minute') unlockAt.setMinutes(unlockAt.getMinutes() + 1)
  if (lockDuration === 'week') unlockAt.setDate(unlockAt.getDate() + 7)
  if (lockDuration === 'month') unlockAt.setMonth(unlockAt.getMonth() + 1)
  return unlockAt.toISOString()
}

function pickRandomPrompts(limit: number): string[] {
  const pool = [...PROMPTS]
  const picked: string[] = []
  while (picked.length < limit && pool.length > 0) {
    const index = Math.floor(Math.random() * pool.length)
    const [item] = pool.splice(index, 1)
    if (item) picked.push(item)
  }
  return picked
}

export function DiaryPage() {
  const { user } = useAuth()
  const userId = user?.id ?? null
  const [entries, setEntries] = useState<DiaryEntry[]>([])
  const [viewMode, setViewMode] = useState<ViewMode>('unlocked')
  const [dayTitle, setDayTitle] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showPromptPanel, setShowPromptPanel] = useState(false)
  const [promptOptions, setPromptOptions] = useState<string[]>([])
  const [selectedEntry, setSelectedEntry] = useState<DiaryEntry | null>(null)
  const [bookDetailTitle, setBookDetailTitle] = useState<string | null>(null)
  const [bookDetailEntries, setBookDetailEntries] = useState<DiaryEntry[]>([])

  const [entryTitle, setEntryTitle] = useState('')
  const [entryText, setEntryText] = useState('')
  const [entryMood, setEntryMood] = useState<Mood>('😊')
  const [entryIntensity, setEntryIntensity] = useState(3)
  const [entryKeywords, setEntryKeywords] = useState('')
  const [entryLockDuration, setEntryLockDuration] = useState<LockDuration>('none')
  const [showStickerPalette, setShowStickerPalette] = useState(false)
  const [selectedSticker, setSelectedSticker] = useState<{ kind: StickerKind; content: string } | null>(null)
  const stickerUploadRef = useRef<HTMLInputElement | null>(null)
  const cropCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const [cropImage, setCropImage] = useState<HTMLImageElement | null>(null)
  const [showCropModal, setShowCropModal] = useState(false)
  const [cropBox, setCropBox] = useState<CropBox | null>(null)
  const [cropSizePercent, setCropSizePercent] = useState(70)
  const [isDraggingCrop, setIsDraggingCrop] = useState(false)
  const cropDragOffsetRef = useRef<{ dx: number; dy: number } | null>(null)
  const cropViewportRef = useRef<CropViewport | null>(null)
  const [selectedPlacedSticker, setSelectedPlacedSticker] = useState<StickerPointer | null>(null)
  const [draggingSticker, setDraggingSticker] = useState<DraggingSticker | null>(null)
  const [draggedEntryId, setDraggedEntryId] = useState<number | null>(null)
  const [typedDetailText, setTypedDetailText] = useState('')
  const typingTimerRef = useRef<number | null>(null)
  const [transformingSticker, setTransformingSticker] = useState<TransformingSticker | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())
  const [syncHint, setSyncHint] = useState('')
  const remoteHydratedRef = useRef(false)
  const skipNextRemoteSaveRef = useRef(false)
  const remoteSaveTimerRef = useRef<number | null>(null)

  const today = useMemo(
    () =>
      new Date().toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      }),
    [],
  )

  const visibleEntries = useMemo(() => {
    if (viewMode === 'bookshelf') return []
    return entries
      .filter((entry) => !entry.status)
      .filter((entry) => (viewMode === 'locked' ? entry.locked : !entry.locked))
      .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
  }, [entries, viewMode])

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNowMs(Date.now())
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!userId) {
      remoteHydratedRef.current = false
      skipNextRemoteSaveRef.current = false
      setSyncHint('')
      return
    }

    let cancelled = false
    remoteHydratedRef.current = false
    setSyncHint('Syncing diary with mid-auth...')

    ;(async () => {
      try {
        const remoteEntries = await fetchDiaryEntriesFromMemos<DiaryEntry>()
        if (cancelled) return
        remoteHydratedRef.current = true

        if (remoteEntries) {
          skipNextRemoteSaveRef.current = true
          setEntries(remoteEntries)
          setSyncHint('Diary synced.')
        } else {
          setSyncHint('No remote diary yet.')
        }
      } catch (error) {
        if (cancelled) return
        remoteHydratedRef.current = true
        console.warn('[DiaryPage] Remote diary load failed.', error)
        setSyncHint('Remote sync unavailable.')
      }
    })()

    return () => {
      cancelled = true
    }
  }, [userId])

  useEffect(() => {
    if (!userId || !remoteHydratedRef.current) return
    if (skipNextRemoteSaveRef.current) {
      skipNextRemoteSaveRef.current = false
      return
    }

    if (remoteSaveTimerRef.current) {
      window.clearTimeout(remoteSaveTimerRef.current)
      remoteSaveTimerRef.current = null
    }

    setSyncHint('Saving diary...')
    remoteSaveTimerRef.current = window.setTimeout(async () => {
      try {
        await saveDiaryEntriesToMemos(entries)
        setSyncHint('Diary saved to mid-auth.')
      } catch (error) {
        console.warn('[DiaryPage] Remote diary save failed.', error)
        const detail = error instanceof Error ? error.message : 'unknown error'
        setSyncHint(`Save to mid-auth failed: ${detail}`)
      } finally {
        remoteSaveTimerRef.current = null
      }
    }, 650)

    return () => {
      if (remoteSaveTimerRef.current) {
        window.clearTimeout(remoteSaveTimerRef.current)
        remoteSaveTimerRef.current = null
      }
    }
  }, [entries, userId])

  const isUnlockReady = (entry: DiaryEntry) =>
    Boolean(entry.locked && entry.unlockTime && Date.parse(entry.unlockTime) <= nowMs)

  const formatUnlockedAt = (value: string | null | undefined) => {
    if (!value) return ''
    const date = new Date(value)
    const yyyy = String(date.getFullYear())
    const mm = String(date.getMonth() + 1).padStart(2, '0')
    const dd = String(date.getDate()).padStart(2, '0')
    const hh = String(date.getHours()).padStart(2, '0')
    const mi = String(date.getMinutes()).padStart(2, '0')
    const ss = String(date.getSeconds()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`
  }

  useEffect(() => {
    if (typingTimerRef.current) {
      window.clearTimeout(typingTimerRef.current)
      typingTimerRef.current = null
    }
    if (!selectedEntry) {
      setTypedDetailText('')
      return
    }

    let index = 0
    const text = selectedEntry.text
    setTypedDetailText('')

    const write = () => {
      index += 1
      setTypedDetailText(text.slice(0, index))
      if (index < text.length) {
        typingTimerRef.current = window.setTimeout(write, 50)
      }
    }

    write()
    return () => {
      if (typingTimerRef.current) {
        window.clearTimeout(typingTimerRef.current)
        typingTimerRef.current = null
      }
    }
  }, [selectedEntry])

  useEffect(() => {
    if (!showCropModal || !cropImage || !cropBox) return
    const canvas = cropCanvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const maxWidth = 460
    const maxHeight = 320
    const scale = Math.min(maxWidth / cropImage.width, maxHeight / cropImage.height, 1)
    const drawWidth = cropImage.width * scale
    const drawHeight = cropImage.height * scale

    canvas.width = Math.round(drawWidth)
    canvas.height = Math.round(drawHeight)
    cropViewportRef.current = { scale, offsetX: 0, offsetY: 0 }

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(cropImage, 0, 0, cropImage.width, cropImage.height, 0, 0, drawWidth, drawHeight)

    const cropX = cropBox.x * scale
    const cropY = cropBox.y * scale
    const cropSize = cropBox.size * scale

    // Darken outside crop area.
    ctx.fillStyle = 'rgba(0, 0, 0, 0.45)'
    ctx.fillRect(0, 0, canvas.width, cropY)
    ctx.fillRect(0, cropY, cropX, cropSize)
    ctx.fillRect(cropX + cropSize, cropY, canvas.width - (cropX + cropSize), cropSize)
    ctx.fillRect(0, cropY + cropSize, canvas.width, canvas.height - (cropY + cropSize))

    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 2
    ctx.strokeRect(cropX, cropY, cropSize, cropSize)
  }, [showCropModal, cropImage, cropBox])

  useEffect(() => {
    if (!isDraggingCrop) return
    const onUp = () => {
      setIsDraggingCrop(false)
      cropDragOffsetRef.current = null
    }
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mouseup', onUp)
    }
  }, [isDraggingCrop])

  useEffect(() => {
    if (!draggingSticker) return
    const onMove = (event: globalThis.MouseEvent) => {
      const { rect, entryId, stickerId } = draggingSticker
      const xPercent = ((event.clientX - rect.left) / rect.width) * 100
      const yPercent = ((event.clientY - rect.top) / rect.height) * 100
      updateEntry(entryId, (entry) => ({
        ...entry,
        stickers: (entry.stickers ?? []).map((sticker) =>
          sticker.id === stickerId
            ? {
                ...sticker,
                xPercent: Math.max(0, Math.min(100, xPercent)),
                yPercent: Math.max(0, Math.min(100, yPercent)),
              }
            : sticker,
        ),
      }))
    }
    const onUp = () => {
      setDraggingSticker(null)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [draggingSticker, entries])

  useEffect(() => {
    if (!transformingSticker) return

    const onMove = (event: globalThis.MouseEvent) => {
      const { entryId, stickerId, mode, centerX, centerY, startAngle, startRotation, startDistance, startScale } =
        transformingSticker

      const dx = event.clientX - centerX
      const dy = event.clientY - centerY
      const currentAngle = Math.atan2(dy, dx)

      if (mode === 'rotate') {
        const deltaDegrees = ((currentAngle - startAngle) * 180) / Math.PI
        transformSticker(entryId, stickerId, { rotation: startRotation + deltaDegrees })
        return
      }

      const safeStartDistance = Math.max(16, startDistance)
      // Use signed radial projection so crossing center won't invert scaling.
      const radialDistance = dx * transformingSticker.startUnitX + dy * transformingSticker.startUnitY
      const safeRadialDistance = Math.max(0, radialDistance)
      const rawScale = startScale * (safeRadialDistance / safeStartDistance)
      const nextScale = Math.max(STICKER_MIN_SCALE, Math.min(STICKER_MAX_SCALE, rawScale))
      transformSticker(entryId, stickerId, { scale: nextScale })
    }

    const onUp = () => {
      setTransformingSticker(null)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)

    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [transformingSticker, entries])

  const books = useMemo(() => {
    const map: Record<string, DiaryEntry[]> = {
      Digested: [],
      Happy: [],
      Sad: [],
      Angry: [],
      Surprised: [],
      Love: [],
    }
    const moodToBook: Record<Mood, keyof typeof map> = {
      '😊': 'Happy',
      '😢': 'Sad',
      '😠': 'Angry',
      '😮': 'Surprised',
      '😍': 'Love',
    }
    entries.forEach((entry) => {
      if (entry.status === 'digested') map.Digested.push(entry)
      if (entry.status === 'archived') map[moodToBook[entry.mood]].push(entry)
    })
    return map
  }, [entries])

  const createNewEntry = () => {
    const title = entryTitle.trim() || dayTitle.trim() || 'Entry'
    const text = entryText.trim()
    if (!text) return

    const keywords = entryKeywords
      .split(',')
      .map((item) => item.trim().replace(/^#/, ''))
      .filter(Boolean)

    const nextEntry: DiaryEntry = {
      id: Date.now(),
      title,
      text,
      mood: entryMood,
      moodIntensity: entryIntensity,
      keywords,
      timestamp: new Date().toISOString(),
      locked: entryLockDuration !== 'none',
      unlockTime: calculateUnlockTime(entryLockDuration),
      unlockedAt: null,
      stickers: [],
    }

    const nextEntries = [nextEntry, ...entries]
    setEntries(nextEntries)
    setShowCreateModal(false)
    resetCreateForm()
  }

  const resetCreateForm = () => {
    setEntryTitle('')
    setEntryText('')
    setEntryMood('😊')
    setEntryIntensity(3)
    setEntryKeywords('')
    setEntryLockDuration('none')
  }

  const openCreateModal = (withPrompt?: string) => {
    setEntryTitle(dayTitle)
    setEntryText(withPrompt ?? '')
    setShowCreateModal(true)
  }

  const markEntryStatus = (id: number, status: EntryStatus) => {
    const nextEntries = entries.map((entry) => (entry.id === id ? { ...entry, status } : entry))
    setEntries(nextEntries)
    setSelectedEntry(null)
  }

  const updateEntry = (id: number, updater: (entry: DiaryEntry) => DiaryEntry) => {
    const nextEntries = entries.map((entry) => (entry.id === id ? updater(entry) : entry))
    setEntries(nextEntries)
    if (selectedEntry?.id === id) {
      const refreshed = nextEntries.find((entry) => entry.id === id)
      if (refreshed) setSelectedEntry(refreshed)
    }
  }

  const placeStickerInDetail = (event: MouseEvent<HTMLDivElement>) => {
    if (!selectedEntry || !selectedSticker) return
    const rect = event.currentTarget.getBoundingClientRect()
    const xPercent = ((event.clientX - rect.left) / rect.width) * 100
    const yPercent = ((event.clientY - rect.top) / rect.height) * 100
    const sticker: StickerItem = {
      id: Date.now(),
      kind: selectedSticker.kind,
      content: selectedSticker.content,
      xPercent: Math.max(0, Math.min(100, xPercent)),
      yPercent: Math.max(0, Math.min(100, yPercent)),
      scale: 1,
      rotation: 0,
    }
    updateEntry(selectedEntry.id, (entry) => ({
      ...entry,
      stickers: [...(entry.stickers ?? []), sticker],
    }))
    setSelectedSticker(null)
  }

  const removeSticker = (entryId: number, stickerId: number) => {
    updateEntry(entryId, (entry) => ({
      ...entry,
      stickers: (entry.stickers ?? []).filter((sticker) => sticker.id !== stickerId),
    }))
  }

  const onUploadSticker = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const content = typeof reader.result === 'string' ? reader.result : ''
      if (content) {
        const image = new Image()
        image.onload = () => {
          const minSide = Math.min(image.width, image.height)
          const startSize = minSide * 0.7
          setCropSizePercent(70)
          setCropBox({
            x: (image.width - startSize) / 2,
            y: (image.height - startSize) / 2,
            size: startSize,
          })
          setCropImage(image)
          setShowCropModal(true)
        }
        image.src = content
      }
      event.target.value = ''
    }
    reader.readAsDataURL(file)
  }

  const saveCroppedSticker = () => {
    if (!cropImage || !cropBox) return
    const exportCanvas = document.createElement('canvas')
    const exportSize = Math.max(96, Math.min(160, Math.round(cropBox.size)))
    exportCanvas.width = exportSize
    exportCanvas.height = exportSize
    const exportContext = exportCanvas.getContext('2d')
    if (!exportContext) return
    exportContext.drawImage(
      cropImage,
      cropBox.x,
      cropBox.y,
      cropBox.size,
      cropBox.size,
      0,
      0,
      exportSize,
      exportSize,
    )
    // Prefer compressed format to avoid oversized diary payloads.
    let content = exportCanvas.toDataURL('image/webp', 0.62)
    if (!content || content === 'data:,') {
      content = exportCanvas.toDataURL('image/jpeg', 0.68)
    }
    if (!content || content === 'data:,') {
      content = exportCanvas.toDataURL('image/png')
    }
    setSelectedSticker({ kind: 'image', content })
    setShowStickerPalette(false)
    setShowCropModal(false)
    setCropImage(null)
    setCropBox(null)
    window.alert('Custom sticker created! Click anywhere to place it.')
  }

  const toImagePointFromCanvasEvent = (
    event: MouseEvent<HTMLCanvasElement>,
    image: HTMLImageElement,
  ): { x: number; y: number } | null => {
    const canvas = cropCanvasRef.current
    const viewport = cropViewportRef.current
    if (!canvas || !viewport) return null
    const rect = canvas.getBoundingClientRect()
    const canvasX = event.clientX - rect.left
    const canvasY = event.clientY - rect.top
    const imageX = (canvasX - viewport.offsetX) / viewport.scale
    const imageY = (canvasY - viewport.offsetY) / viewport.scale
    return {
      x: Math.max(0, Math.min(image.width, imageX)),
      y: Math.max(0, Math.min(image.height, imageY)),
    }
  }

  const onCropCanvasMouseDown = (event: MouseEvent<HTMLCanvasElement>) => {
    if (!cropImage || !cropBox) return
    const imagePoint = toImagePointFromCanvasEvent(event, cropImage)
    if (!imagePoint) return
    const inside =
      imagePoint.x >= cropBox.x &&
      imagePoint.x <= cropBox.x + cropBox.size &&
      imagePoint.y >= cropBox.y &&
      imagePoint.y <= cropBox.y + cropBox.size
    if (!inside) return
    setIsDraggingCrop(true)
    cropDragOffsetRef.current = {
      dx: imagePoint.x - cropBox.x,
      dy: imagePoint.y - cropBox.y,
    }
  }

  const onCropCanvasMouseMove = (event: MouseEvent<HTMLCanvasElement>) => {
    if (!isDraggingCrop || !cropImage || !cropBox) return
    const imagePoint = toImagePointFromCanvasEvent(event, cropImage)
    const dragOffset = cropDragOffsetRef.current
    if (!imagePoint || !dragOffset) return

    const maxX = cropImage.width - cropBox.size
    const maxY = cropImage.height - cropBox.size
    const nextX = Math.max(0, Math.min(maxX, imagePoint.x - dragOffset.dx))
    const nextY = Math.max(0, Math.min(maxY, imagePoint.y - dragOffset.dy))
    setCropBox((current) => (current ? { ...current, x: nextX, y: nextY } : current))
  }

  const onCropSizeChange = (nextPercent: number) => {
    setCropSizePercent(nextPercent)
    setCropBox((current) => {
      if (!current || !cropImage) return current
      const minSide = Math.min(cropImage.width, cropImage.height)
      const nextSize = Math.max(minSide * 0.25, Math.min(minSide, (minSide * nextPercent) / 100))
      const centerX = current.x + current.size / 2
      const centerY = current.y + current.size / 2
      const nextX = Math.max(0, Math.min(cropImage.width - nextSize, centerX - nextSize / 2))
      const nextY = Math.max(0, Math.min(cropImage.height - nextSize, centerY - nextSize / 2))
      return { x: nextX, y: nextY, size: nextSize }
    })
  }

  const selectPlacedSticker = (entryId: number, stickerId: number) => {
    setSelectedPlacedSticker((current) =>
      current?.entryId === entryId && current.stickerId === stickerId ? null : { entryId, stickerId },
    )
  }

  const transformSticker = (entryId: number, stickerId: number, change: Partial<Pick<StickerItem, 'scale' | 'rotation'>>) => {
    updateEntry(entryId, (entry) => ({
      ...entry,
      stickers: (entry.stickers ?? []).map((sticker) =>
        sticker.id === stickerId
          ? {
              ...sticker,
              scale: Math.max(STICKER_MIN_SCALE, Math.min(STICKER_MAX_SCALE, change.scale ?? sticker.scale)),
              rotation: change.rotation ?? sticker.rotation,
            }
          : sticker,
      ),
    }))
  }

  const startTransformSticker = (
    event: MouseEvent<HTMLButtonElement>,
    entryId: number,
    sticker: StickerItem,
    mode: StickerTransformMode,
  ) => {
    event.preventDefault()
    event.stopPropagation()

    const stickerElement = event.currentTarget.closest('.diary-placed-sticker') as HTMLElement | null
    if (!stickerElement) return
    const rect = stickerElement.getBoundingClientRect()
    const centerX = rect.left + rect.width / 2
    const centerY = rect.top + rect.height / 2
    const dx = event.clientX - centerX
    const dy = event.clientY - centerY
    const distance = Math.hypot(dx, dy)
    const safeDistance = Math.max(1, distance)

    setTransformingSticker({
      entryId,
      stickerId: sticker.id,
      mode,
      centerX,
      centerY,
      startAngle: Math.atan2(dy, dx),
      startRotation: sticker.rotation,
      startDistance: distance,
      startScale: sticker.scale,
      startUnitX: dx / safeDistance,
      startUnitY: dy / safeDistance,
    })
  }

  const placeStickerInCard = (event: MouseEvent<HTMLElement>, entryId: number) => {
    if (!selectedSticker) return
    const rect = event.currentTarget.getBoundingClientRect()
    const xPercent = ((event.clientX - rect.left) / rect.width) * 100
    const yPercent = ((event.clientY - rect.top) / rect.height) * 100
    const sticker: StickerItem = {
      id: Date.now(),
      kind: selectedSticker.kind,
      content: selectedSticker.content,
      xPercent: Math.max(0, Math.min(100, xPercent)),
      yPercent: Math.max(0, Math.min(100, yPercent)),
      scale: 1,
      rotation: 0,
    }
    updateEntry(entryId, (entry) => ({
      ...entry,
      stickers: [...(entry.stickers ?? []), sticker],
    }))
    setSelectedSticker(null)
  }

  const reorderEntries = (sourceId: number, targetId: number) => {
    if (sourceId === targetId) return
    const isVisible = (entry: DiaryEntry) =>
      !entry.status && (viewMode === 'locked' ? entry.locked : !entry.locked) && viewMode !== 'bookshelf'

    const lookup = new Map(entries.map((entry) => [entry.id, entry]))
    const visibleIds = entries.filter(isVisible).map((entry) => entry.id)
    if (!visibleIds.includes(sourceId) || !visibleIds.includes(targetId)) return

    const orderedVisible = visibleIds.filter((id) => id !== sourceId)
    const targetIndex = orderedVisible.indexOf(targetId)
    orderedVisible.splice(targetIndex, 0, sourceId)

    let cursor = 0
    const nextEntries = entries.map((entry) => {
      if (!isVisible(entry)) return entry
      const nextId = orderedVisible[cursor]
      cursor += 1
      return nextId ? lookup.get(nextId) ?? entry : entry
    })
    setEntries(nextEntries)
  }

  const renderSticker = (entryId: number, sticker: StickerItem) => {
    const isSelected = selectedPlacedSticker?.entryId === entryId && selectedPlacedSticker.stickerId === sticker.id
    return (
      <button
        type="button"
        key={sticker.id}
        className={`diary-placed-sticker${sticker.kind === 'text' ? ' text' : ''}${isSelected ? ' selected' : ''}`}
        style={{
          left: `${sticker.xPercent}%`,
          top: `${sticker.yPercent}%`,
          transform: `translate(-50%, -50%) scale(${sticker.scale}) rotate(${sticker.rotation}deg)`,
        }}
        onClick={(event) => {
          event.stopPropagation()
        }}
        onDoubleClick={(event) => {
          event.stopPropagation()
          selectPlacedSticker(entryId, sticker.id)
        }}
      >
        {sticker.kind === 'image' ? <img src={sticker.content} alt="custom sticker" /> : sticker.content}
        <span
          className="diary-sticker-edge-handle"
          onMouseDown={(event) => {
            if (!isSelected) return
            event.preventDefault()
            event.stopPropagation()
            const parent = (event.currentTarget.closest('.diary-detail-canvas') ??
              event.currentTarget.closest('.diary-entry-card')) as HTMLElement | null
            if (!parent) return
            setDraggingSticker({
              entryId,
              stickerId: sticker.id,
              rect: parent.getBoundingClientRect(),
            })
          }}
        />
        {isSelected ? (
          <span className="diary-sticker-controls" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              title="Rotate"
              onMouseDown={(event) => startTransformSticker(event, entryId, sticker, 'rotate')}
            >
              🔄
            </button>
            <button
              type="button"
              title="Scale"
              onMouseDown={(event) => startTransformSticker(event, entryId, sticker, 'scale')}
            >
              🔍
            </button>
            <button
              type="button"
              title="Delete"
              onClick={() => {
                if (window.confirm('Delete this sticker?')) {
                  removeSticker(entryId, sticker.id)
                  setSelectedPlacedSticker(null)
                }
              }}
            >
              🗑️
            </button>
          </span>
        ) : null}
      </button>
    )
  }

  const unlockEntryManually = (id: number) => {
    updateEntry(id, (entry) => ({
      ...entry,
      locked: false,
      unlockedAt: new Date().toISOString(),
    }))
  }

  const moodClassName = (mood: Mood) => {
    if (mood === '😊') return 'diary-mood-bg-happy'
    if (mood === '😢') return 'diary-mood-bg-sad'
    if (mood === '😠') return 'diary-mood-bg-angry'
    if (mood === '😮') return 'diary-mood-bg-surprised'
    return 'diary-mood-bg-love'
  }

  return (
    <section className="diary-page">
      <div className="diary-sticker-container">
        <button
          type="button"
          className="diary-sticker-mode-btn"
          onClick={() => setShowStickerPalette((value) => !value)}
        >
          🗃️ Sticker
        </button>
        <div className={`diary-sticker-palette${showStickerPalette ? '' : ' hidden'}`}>
          <div className="diary-sticker-section">
            <span>Emojis</span>
            {STICKER_EMOJIS.map((emoji) => (
              <button
                type="button"
                key={emoji}
                className={`diary-sticker-item${selectedSticker?.kind === 'emoji' && selectedSticker.content === emoji ? ' selected' : ''}`}
                onClick={() => {
                  setSelectedSticker({ kind: 'emoji', content: emoji })
                  setShowStickerPalette(false)
                }}
              >
                {emoji}
              </button>
            ))}
          </div>
          <div className="diary-sticker-section">
            <span>Text</span>
            {STICKER_TEXTS.map((text) => (
              <button
                type="button"
                key={text}
                className={`diary-sticker-item text${selectedSticker?.kind === 'text' && selectedSticker.content === text ? ' selected' : ''}`}
                onClick={() => {
                  setSelectedSticker({ kind: 'text', content: text })
                  setShowStickerPalette(false)
                }}
              >
                {text}
              </button>
            ))}
          </div>
          <button type="button" className="diary-sticker-upload-btn" onClick={() => stickerUploadRef.current?.click()}>
            Upload
          </button>
          <input ref={stickerUploadRef} type="file" accept="image/*" hidden onChange={onUploadSticker} />
        </div>
      </div>

      <header className="diary-island">
        <div className="diary-date">{today}</div>
        <input
          className="diary-title-input"
          placeholder="Name your day"
          value={dayTitle}
          onChange={(e) => {
            setDayTitle(e.target.value)
            setEntryTitle(e.target.value)
          }}
        />
      </header>
      {syncHint ? <p className="diary-sync-hint">{syncHint}</p> : null}

      <div className="diary-toggle-row">
        <button
          type="button"
          className={`diary-toggle-btn${viewMode === 'unlocked' ? ' active' : ''}`}
          onClick={() => setViewMode('unlocked')}
        >
          Unlocked
        </button>
        <button
          type="button"
          className={`diary-toggle-btn${viewMode === 'locked' ? ' active' : ''}`}
          onClick={() => setViewMode('locked')}
        >
          Locked
        </button>
        <button
          type="button"
          className={`diary-toggle-btn${viewMode === 'bookshelf' ? ' active' : ''}`}
          onClick={() => setViewMode('bookshelf')}
        >
          📚 Bookshelf
        </button>
      </div>

      {viewMode === 'bookshelf' ? (
        <div className="diary-bookshelf-grid">
          {Object.entries(books).map(([title, list]) =>
            list.length > 0 ? (
              <button
                type="button"
                key={title}
                className="diary-book"
                onClick={() => {
                  setBookDetailTitle(title)
                  setBookDetailEntries(list)
                }}
              >
                <span className="diary-book-spine" />
                <span className="diary-book-title">{title}</span>
                <span className="diary-book-count">{list.length}</span>
              </button>
            ) : null,
          )}
          {Object.values(books).every((list) => list.length === 0) ? (
            <p className="diary-empty-state">No books yet. Archive or digest entries to fill your shelf.</p>
          ) : null}
        </div>
      ) : (
        <main className="diary-entry-list">
          {visibleEntries.length === 0 ? (
            <p className="diary-empty-state">No entries here yet. Start writing!</p>
          ) : (
            visibleEntries.map((entry) => (
              <article
                key={entry.id}
                className={`diary-entry-card${entry.locked ? ' locked' : ''}`}
                draggable
                onDragStart={() => setDraggedEntryId(entry.id)}
                onDragEnd={() => setDraggedEntryId(null)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => {
                  if (draggedEntryId) reorderEntries(draggedEntryId, entry.id)
                  setDraggedEntryId(null)
                }}
                onClick={(event) => {
                  if (entry.locked) return
                  const target = event.target as HTMLElement
                  if (target.tagName === 'CANVAS') return
                  if (target.closest('.diary-placed-sticker') || target.closest('.diary-sticker-controls')) return
                  if (selectedSticker) {
                    placeStickerInCard(event, entry.id)
                    return
                  }
                  setSelectedEntry(entry)
                }}
              >
                {entry.locked ? (
                  <div className="diary-entry-lock-state">
                    <h3 className="diary-locked-title">{entry.title}</h3>
                    <p>This entry is locked until {new Date(entry.unlockTime ?? '').toLocaleString()}</p>
                    {isUnlockReady(entry) ? (
                      <button
                        type="button"
                        className="diary-unlock-ready-btn"
                        onClick={(event) => {
                          event.stopPropagation()
                          unlockEntryManually(entry.id)
                        }}
                      >
                        🔓 Unlock
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <>
                    <div className="diary-entry-header">
                      <h3>{entry.title}</h3>
                      <div className="diary-entry-mood">
                        <span>{entry.mood}</span>
                        <span className="diary-mood-level">Level {entry.moodIntensity}</span>
                      </div>
                    </div>
                    <p className="diary-entry-text">{entry.text}</p>
                    <footer className="diary-entry-footer">
                      <div className="diary-entry-tags">
                        {entry.keywords.map((tag) => (
                          <span key={`${entry.id}-${tag}`}>#{tag}</span>
                        ))}
                      </div>
                      <div className="diary-entry-time-col">
                        {entry.unlockedAt ? (
                          <span className="diary-unlocked-at">Unlocked at {formatUnlockedAt(entry.unlockedAt)}</span>
                        ) : null}
                        <time>{new Date(entry.timestamp).toLocaleString()}</time>
                      </div>
                    </footer>
                    {(entry.stickers ?? []).map((sticker) => renderSticker(entry.id, sticker))}
                    {entry.unlockTime ? <ScratchRevealOverlay /> : null}
                  </>
                )}
              </article>
            ))
          )}
        </main>
      )}

      <div className="diary-fab-row">
        <button
          type="button"
          className="diary-fab"
          title="Reflection spark"
          onClick={() => {
            setPromptOptions(pickRandomPrompts(5))
            setShowPromptPanel(true)
          }}
        >
          ✨
        </button>
        <button type="button" className="diary-fab" title="New entry" onClick={() => openCreateModal()}>
          +
        </button>
      </div>

      <aside className={`diary-prompt-panel${showPromptPanel ? ' active' : ''}`}>
        <button type="button" className="diary-close-btn" onClick={() => setShowPromptPanel(false)}>
          ×
        </button>
        <h3>Pick a Reflection Spark</h3>
        <ul>
          {promptOptions.map((prompt) => (
            <li key={prompt}>
              <button
                type="button"
                onClick={() => {
                  setShowPromptPanel(false)
                  setShowCreateModal(true)
                  setEntryTitle(dayTitle)
                  setEntryText((current) => (current ? `${current}\n\n${prompt}` : prompt))
                }}
              >
                {prompt}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className={`diary-modal${showCreateModal ? ' active' : ''}`} role="dialog" aria-modal="true">
        <div className="diary-modal-content">
          <button type="button" className="diary-close-btn" onClick={() => setShowCreateModal(false)}>
            ×
          </button>
          <h2>New Entry</h2>
          <input
            className="diary-modal-title"
            placeholder="Title your day"
            value={entryTitle}
            onChange={(e) => {
              setEntryTitle(e.target.value)
              setDayTitle(e.target.value)
            }}
          />
          <textarea
            placeholder="What's on your mind?"
            value={entryText}
            onChange={(e) => setEntryText(e.target.value)}
          />
          <div className="diary-form-block">
            <span>Mood</span>
            <div className="diary-mood-row">
              {MOODS.map((mood) => (
                <button
                  type="button"
                  key={mood}
                  className={entryMood === mood ? 'selected' : ''}
                  onClick={() => setEntryMood(mood)}
                >
                  {mood}
                </button>
              ))}
            </div>
          </div>
          <div className="diary-form-block">
            <label htmlFor="diary-intensity">Intensity</label>
            <input
              id="diary-intensity"
              type="range"
              min={1}
              max={5}
              value={entryIntensity}
              onChange={(e) => setEntryIntensity(Number(e.target.value))}
            />
          </div>
          <input
            placeholder="Add keywords (e.g., #work, #family)"
            value={entryKeywords}
            onChange={(e) => setEntryKeywords(e.target.value)}
          />
          <div className="diary-form-block">
            <span>Lock for</span>
            <div className="diary-lock-row">
              {(['none', 'minute', 'week', 'month'] as const).map((duration) => (
                <button
                  key={duration}
                  type="button"
                  className={entryLockDuration === duration ? 'selected' : ''}
                  onClick={() => setEntryLockDuration(duration)}
                >
                  {duration === 'none'
                    ? 'None'
                    : duration === 'minute'
                      ? '1 Minute'
                      : duration === 'week'
                        ? '1 Week'
                        : '1 Month'}
                </button>
              ))}
            </div>
          </div>
          <button type="button" className="diary-save-btn" onClick={createNewEntry}>
            Save Entry
          </button>
        </div>
      </div>

      <div className={`diary-modal${showCropModal ? ' active' : ''}`} role="dialog" aria-modal="true">
        {showCropModal ? (
          <div className="diary-modal-content diary-crop-modal">
            <h3>Crop Your Sticker</h3>
            <div className="diary-crop-canvas-wrap">
              <canvas
                ref={cropCanvasRef}
                className={isDraggingCrop ? 'dragging' : ''}
                onMouseDown={onCropCanvasMouseDown}
                onMouseMove={onCropCanvasMouseMove}
                onMouseUp={() => {
                  setIsDraggingCrop(false)
                  cropDragOffsetRef.current = null
                }}
                onMouseLeave={() => {
                  if (isDraggingCrop) return
                  cropDragOffsetRef.current = null
                }}
              />
            </div>
            <div className="diary-crop-controls">
              <label htmlFor="diary-crop-size">Crop size</label>
              <input
                id="diary-crop-size"
                type="range"
                min={25}
                max={100}
                value={cropSizePercent}
                onChange={(event) => onCropSizeChange(Number(event.target.value))}
              />
              <p>Drag the white box to reposition. Use the slider to adjust the crop size.</p>
            </div>
            <div className="diary-crop-actions">
              <button
                type="button"
                onClick={() => {
                  setShowCropModal(false)
                  setCropImage(null)
                  setCropBox(null)
                }}
              >
                Cancel
              </button>
              <button type="button" onClick={saveCroppedSticker}>
                Create Sticker
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <div className={`diary-modal${selectedEntry ? ' active' : ''}`} role="dialog" aria-modal="true">
        {selectedEntry ? (
          <div className={`diary-modal-content diary-detail ${moodClassName(selectedEntry.mood)}`}>
            <button type="button" className="diary-close-btn" onClick={() => setSelectedEntry(null)}>
              ×
            </button>
            <h2>{selectedEntry.title}</h2>
            <div className="diary-detail-mood">{selectedEntry.mood}</div>
            <p className="diary-detail-level">Mood Intensity: Level {selectedEntry.moodIntensity}</p>
            <div className="diary-detail-canvas" onClick={placeStickerInDetail}>
              {(selectedEntry.stickers ?? []).map((sticker) => (
                renderSticker(selectedEntry.id, sticker)
              ))}
              <p className="diary-detail-text">{typedDetailText}</p>
              <div className="diary-detail-tags">
                {selectedEntry.keywords.map((tag) => (
                  <span key={`${selectedEntry.id}-detail-${tag}`}>#{tag}</span>
                ))}
              </div>
            </div>
            {selectedSticker ? <p className="diary-sticker-hint">Sticker selected. Click the canvas to place it.</p> : null}
            {!selectedEntry.status ? (
              <div className="diary-detail-actions">
                <button
                  type="button"
                  onClick={() => {
                    markEntryStatus(selectedEntry.id, 'digested')
                    window.alert('This memory has been moved to your "Digested" book.')
                  }}
                >
                  🗑️ Digested
                </button>
                <button
                  type="button"
                  onClick={() => {
                    markEntryStatus(selectedEntry.id, 'archived')
                    window.alert('This memory has been archived to its mood book!')
                  }}
                >
                  💎 Archived
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className={`diary-modal${bookDetailTitle ? ' active' : ''}`} role="dialog" aria-modal="true">
        {bookDetailTitle ? (
          <div className="diary-modal-content diary-book-detail">
            <button type="button" className="diary-close-btn" onClick={() => setBookDetailTitle(null)}>
              ×
            </button>
            <h2>
              {bookDetailTitle} ({bookDetailEntries.length})
            </h2>
            <div className="diary-book-entry-list">
              {bookDetailEntries.map((entry) => (
                <button
                  key={`book-entry-${entry.id}`}
                  type="button"
                  className="diary-book-entry"
                  onClick={() => {
                    setBookDetailTitle(null)
                    setSelectedEntry(entry)
                  }}
                >
                  <h4>{entry.title}</h4>
                  <p>{entry.text.length > 100 ? `${entry.text.slice(0, 100)}...` : entry.text}</p>
                  <time>{new Date(entry.timestamp).toLocaleDateString()}</time>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
