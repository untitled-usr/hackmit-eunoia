export interface OceanBottle {
  x: number
  y: number
  vx: number
  vy: number
  float: number
  size: number
  text: string
}

type WaveSettings = {
  sp1: number
  sp2: number
  wl1: number
  wl2: number
  amp1Factor: number
  amp2Factor: number
}

type BottleSettings = {
  vxMin: number
  vxMax: number
  floatStep: number
  yDriftAmp: number
  hoverDelayMs: number
}

type SeaWindowSettings = {
  minFactor: number
  maxFactor: number
}

export class OceanScene {
  canvas: HTMLCanvasElement
  ctx: CanvasRenderingContext2D
  running = false
  time = 0
  bottles: OceanBottle[] = []
  onPickup: ((text: string) => void) | null = null
  dpr: number
  settings: {
    wave: WaveSettings
    bottle: BottleSettings
    seaWindow: SeaWindowSettings
  }
  pointer: { x: number | null; y: number | null; inside: boolean }
  hover: {
    candidate: number
    since: number
    index: number
    show: boolean
  }
  prevW: number | null = null
  prevH: number | null = null
  amp1 = 0
  amp2 = 0
  seaMin = 0
  seaMax = 0
  hoverEl: HTMLDivElement | null = null

  private readonly onResize: () => void
  private readonly onMouseMove: (e: MouseEvent) => void
  private readonly onMouseLeave: () => void
  private readonly onClick: (e: MouseEvent) => void

  constructor(canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      throw new Error('OceanScene: 2d context unavailable')
    }
    this.canvas = canvas
    this.ctx = ctx
    this.dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
    this.settings = {
      wave: {
        sp1: 0.48,
        sp2: 0.36,
        wl1: 120,
        wl2: 180,
        amp1Factor: 0.05,
        amp2Factor: 0.04,
      },
      bottle: {
        vxMin: 0.08,
        vxMax: 0.32,
        floatStep: 0.012,
        yDriftAmp: 0.24,
        hoverDelayMs: 150,
      },
      seaWindow: { minFactor: 0.5, maxFactor: 0.8 },
    }
    this.pointer = { x: null, y: null, inside: false }
    this.hover = { candidate: -1, since: 0, index: -1, show: false }

    this.onResize = this.resize.bind(this)
    this.onMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      this.pointer.x = e.clientX - rect.left
      this.pointer.y = e.clientY - rect.top
      this.pointer.inside = true
      const idx = this.pickBottleAt(this.pointer.x, this.pointer.y)
      if (idx !== this.hover.candidate) {
        this.hover.candidate = idx
        this.hover.since = performance.now()
        if (idx === -1) {
          this.hover.index = -1
          this.hover.show = false
        }
      }
    }
    this.onMouseLeave = () => {
      this.pointer.x = null
      this.pointer.y = null
      this.pointer.inside = false
      this.hover.candidate = -1
      this.hover.index = -1
      this.hover.show = false
      if (this.hoverEl) {
        this.hoverEl.style.opacity = '0'
      }
    }
    this.onClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      const idx = this.pickBottleAt(x, y)
      if (idx > -1 && this.onPickup) {
        this.onPickup(this.bottles[idx].text)
      }
    }

    window.addEventListener('resize', this.onResize)
    canvas.addEventListener('mousemove', this.onMouseMove)
    canvas.addEventListener('mouseleave', this.onMouseLeave)
    canvas.addEventListener('click', this.onClick)

    const hint = document.createElement('div')
    hint.className = 'glass rounded-md px-2 py-1 text-xs text-slate-700'
    hint.style.position = 'fixed'
    hint.style.opacity = '0'
    hint.style.transition = 'opacity .15s ease-out, transform .15s ease-out'
    hint.style.pointerEvents = 'none'
    hint.style.whiteSpace = 'nowrap'
    hint.style.transform = 'translate(-50%, 0)'
    hint.style.zIndex = '1000'
    document.body.appendChild(hint)
    this.hoverEl = hint
    this.resize()
  }

  destroy(): void {
    this.stop()
    window.removeEventListener('resize', this.onResize)
    this.canvas.removeEventListener('mousemove', this.onMouseMove)
    this.canvas.removeEventListener('mouseleave', this.onMouseLeave)
    this.canvas.removeEventListener('click', this.onClick)
    if (this.hoverEl?.parentNode) {
      this.hoverEl.parentNode.removeChild(this.hoverEl)
    }
    this.hoverEl = null
  }

  start(): void {
    if (this.running) return
    this.running = true
    this.time = 0
    this.loop()
  }

  stop(): void {
    this.running = false
  }

  addBottle(text: string): void {
    const w = this.canvas.width / this.dpr
    const h = this.canvas.height / this.dpr
    const size = Math.max(22, Math.min(32, h / 16))
    const bw = size * 1.2
    const bh = size * 1.6
    const hx = bw / 2
    const hy = bh / 2
    const seaMin = this.seaMin + hy
    const seaMax = this.seaMax - hy
    const low = Math.max(hy, Math.min(seaMin, seaMax))
    const high = Math.min(h - hy, Math.max(seaMin, seaMax))
    const b: OceanBottle = {
      x: Math.random() * (w - bw) + hx,
      y: Math.random() * (high - low) + low,
      vx:
        (Math.random() * (this.settings.bottle.vxMax - this.settings.bottle.vxMin) +
          this.settings.bottle.vxMin) *
        (Math.random() < 0.5 ? -1 : 1),
      vy: 0,
      float: Math.random() * Math.PI * 2,
      size,
      text,
    }
    this.bottles.push(b)
    if (this.bottles.length > 18) this.bottles.shift()
  }

  resize(): void {
    const cssW = this.canvas.clientWidth
    const cssH = this.canvas.clientHeight
    const w = Math.floor(cssW * this.dpr)
    const h = Math.floor(cssH * this.dpr)
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w
      this.canvas.height = h
    }
    this.ctx.setTransform(1, 0, 0, 1, 0, 0)
    this.ctx.scale(this.dpr, this.dpr)
    const ch = this.canvas.height / this.dpr
    this.amp1 = Math.max(8, ch * this.settings.wave.amp1Factor)
    this.amp2 = Math.max(7, ch * this.settings.wave.amp2Factor)
    const cw = this.canvas.width / this.dpr
    this.seaMin = ch * this.settings.seaWindow.minFactor
    this.seaMax = ch * this.settings.seaWindow.maxFactor
    const oldW = this.prevW
    const oldH = this.prevH
    if (oldW && oldH && (oldW !== cw || oldH !== ch)) {
      const sx = cw / oldW
      const sy = ch / oldH
      const newSize = Math.max(22, Math.min(32, ch / 16))
      for (let i = 0; i < this.bottles.length; i++) {
        const b = this.bottles[i]
        b.x *= sx
        b.y *= sy
        b.size = newSize
        const bw = b.size * 1.2
        const bh = b.size * 1.6
        const hx = bw / 2
        const hy = bh / 2
        if (b.x < hx) b.x = hx
        if (b.x > cw - hx) b.x = cw - hx
        const smin = this.seaMin + hy
        const smax = this.seaMax - hy
        if (b.y < smin) b.y = smin
        if (b.y > smax) b.y = smax
      }
    }
    this.prevW = cw
    this.prevH = ch
    if (this.hoverEl) {
      this.hoverEl.style.opacity = '0'
    }
  }

  private renderHoverTip(): void {
    if (!this.hoverEl) return
    if (this.hover.show && this.hover.index > -1) {
      const b = this.bottles[this.hover.index]
      this.hoverEl.textContent = b.text || '🍾 Click to pick up'
      const rect = this.canvas.getBoundingClientRect()
      const cww = window.innerWidth
      const chh = window.innerHeight
      const ew = this.hoverEl.offsetWidth || 160
      const eh = this.hoverEl.offsetHeight || 28
      let cx = rect.left + b.x
      let ty = rect.top + b.y - (eh + 10)
      if (ty < 8) ty = rect.top + b.y + 10
      if (ty + eh > chh - 8) ty = Math.max(8, chh - eh - 8)
      if (cx - ew / 2 < 8) cx = ew / 2 + 8
      if (cx + ew / 2 > cww - 8) cx = cww - ew / 2 - 8
      this.hoverEl.style.left = `${cx}px`
      this.hoverEl.style.top = `${ty}px`
      this.hoverEl.style.opacity = '1'
    } else {
      this.hoverEl.style.opacity = '0'
    }
  }

  private pickBottleAt(x: number | null, y: number | null): number {
    if (x == null || y == null) return -1
    for (let i = 0; i < this.bottles.length; i++) {
      const b = this.bottles[i]
      const bw = b.size * 1.2
      const bh = b.size * 1.6
      if (x >= b.x - bw / 2 && x <= b.x + bw / 2 && y >= b.y - bh && y <= b.y + bh / 2) {
        return i
      }
    }
    return -1
  }

  private updateHover(now: number): void {
    const idx = this.hover.candidate
    if (idx > -1) {
      if (now - this.hover.since >= this.settings.bottle.hoverDelayMs) {
        this.hover.index = idx
        this.hover.show = true
      }
    } else {
      this.hover.index = -1
      this.hover.show = false
    }
  }

  private drawWaves(t: number): void {
    const ctx = this.ctx
    const w = this.canvas.width / this.dpr
    const h = this.canvas.height / this.dpr
    ctx.clearRect(0, 0, w, h)
    const g = ctx.createLinearGradient(0, 0, 0, h)
    g.addColorStop(0, 'rgba(164, 203, 255, .35)')
    g.addColorStop(1, 'rgba(255, 255, 255, .6)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, w, h)
    ctx.beginPath()
    const y1 = h * 0.55
    const a1 = this.amp1
    const wl1 = this.settings.wave.wl1
    const sp1 = this.settings.wave.sp1
    ctx.moveTo(0, h)
    for (let x = 0; x <= w; x += 3) {
      const y = y1 + Math.sin(x / wl1 + t * sp1) * a1
      ctx.lineTo(x, y)
    }
    ctx.lineTo(w, h)
    ctx.closePath()
    ctx.fillStyle = 'rgba(147,197,253,.45)'
    ctx.fill()
    ctx.beginPath()
    const y2 = h * 0.6
    const a2 = this.amp2
    const wl2 = this.settings.wave.wl2
    const sp2 = this.settings.wave.sp2
    ctx.moveTo(0, h)
    for (let x = 0; x <= w; x += 3) {
      const y = y2 + Math.sin(x / wl2 + t * sp2 + Math.PI / 3) * a2
      ctx.lineTo(x, y)
    }
    ctx.lineTo(w, h)
    ctx.closePath()
    ctx.fillStyle = 'rgba(96,165,250,.5)'
    ctx.fill()
  }

  private drawBottles(): void {
    const ctx = this.ctx
    const w = this.canvas.width / this.dpr
    const h = this.canvas.height / this.dpr
    ctx.font = `${Math.floor(Math.max(22, Math.min(32, h / 16)))}px system-ui, -apple-system, Segoe UI, Roboto`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    this.updateHover(performance.now())
    for (let i = 0; i < this.bottles.length; i++) {
      const b = this.bottles[i]
      b.float += this.settings.bottle.floatStep
      b.x += b.vx
      b.y += Math.sin(b.float) * this.settings.bottle.yDriftAmp
      const bw = b.size * 1.2
      const bh = b.size * 1.6
      const hx = bw / 2
      const hy = bh / 2
      if (b.x < hx) {
        b.x = hx
        b.vx = Math.abs(b.vx)
      }
      if (b.x > w - hx) {
        b.x = w - hx
        b.vx = -Math.abs(b.vx)
      }
      const seaMin = this.seaMin + hy
      const seaMax = this.seaMax - hy
      if (b.y < seaMin) b.y = seaMin
      if (b.y > seaMax) b.y = seaMax
      ctx.save()
      ctx.translate(b.x, b.y)
      ctx.rotate(Math.sin(b.float) * 0.06)
      ctx.fillStyle = '#0f172a'
      ctx.fillText('🍾', 0, 0)
      ctx.restore()
    }
    this.renderHoverTip()
  }

  private loop = (): void => {
    if (!this.running) return
    this.time += 0.016
    this.drawWaves(this.time)
    this.drawBottles()
    requestAnimationFrame(this.loop)
  }
}
