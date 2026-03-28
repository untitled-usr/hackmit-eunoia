import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from 'react'
import { OceanScene } from '../lib/OceanScene'

export type OceanCanvasHandle = {
  addBottle: (text: string) => void
}

type OceanCanvasProps = {
  onPickup: (text: string) => void
  seedBottles?: string[]
}

export const OceanCanvas = forwardRef<OceanCanvasHandle, OceanCanvasProps>(
  function OceanCanvas({ onPickup, seedBottles = [] }, ref) {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const sceneRef = useRef<OceanScene | null>(null)
    const onPickupRef = useRef(onPickup)

    useEffect(() => {
      onPickupRef.current = onPickup
    }, [onPickup])

    useImperativeHandle(ref, () => ({
      addBottle: (text: string) => {
        sceneRef.current?.addBottle(text)
      },
    }))

    useEffect(() => {
      const canvas = canvasRef.current
      if (!canvas) return
      const scene = new OceanScene(canvas)
      scene.onPickup = (text) => onPickupRef.current(text)
      sceneRef.current = scene
      scene.start()
      for (const t of seedBottles) {
        scene.addBottle(t)
      }
      return () => {
        scene.destroy()
        sceneRef.current = null
      }
    }, [seedBottles])

    return (
      <canvas
        ref={canvasRef}
        id="ocean-canvas"
        className="block h-[360px] w-full md:h-[480px]"
      />
    )
  },
)
