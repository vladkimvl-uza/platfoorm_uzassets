/**
 * useNumberTween — плавная анимация числа от старого к новому значению.
 *
 * Использование:
 *   import { useNumberTween } from '@/composables/useNumberTween'
 *   const tweenedDebt = useNumberTween(() => debt.value, { duration: 700 })
 *   // в template: {{ tweenedDebt.toFixed(2) }}
 *
 * Питается computed-источником. При его смене запускает RAF-loop с
 * cubic-bezier-подобным easing (ease-out-cubic). Возвращает ref<number>
 * который меняется КАЖДЫЙ кадр пока идёт анимация.
 *
 * Pack 7.44 — Variant A (Smooth) motion system
 */
import { ref, watch, type Ref, type WatchSource } from 'vue'

interface TweenOpts {
  /** Длительность анимации в миллисекундах. По умолчанию 700ms. */
  duration?: number
  /** Кастомная easing-функция (t: 0..1 → 0..1). По умолчанию ease-out-cubic. */
  easing?: (t: number) => number
  /** Если разница между старым и новым < threshold — пропускаем анимацию. */
  threshold?: number
}

/** ease-out-cubic — мягкий accent в начале, плавный финиш */
const easeOutCubic = (t: number): number => 1 - Math.pow(1 - t, 3)

export function useNumberTween(
  source: WatchSource<number>,
  opts: TweenOpts = {}
): Ref<number> {
  const duration = opts.duration ?? 700
  const easing = opts.easing ?? easeOutCubic
  const threshold = opts.threshold ?? 0.001

  const current = ref<number>(0)
  let rafId: number | null = null
  let startVal = 0
  let endVal = 0
  let startTime = 0

  function frame(now: number) {
    const elapsed = now - startTime
    const t = Math.min(1, elapsed / duration)
    const eased = easing(t)
    current.value = startVal + (endVal - startVal) * eased
    if (t < 1) {
      rafId = requestAnimationFrame(frame)
    } else {
      current.value = endVal
      rafId = null
    }
  }

  watch(
    source,
    (newVal, oldVal) => {
      const nv = Number(newVal) || 0
      const ov = Number(oldVal ?? 0) || 0
      if (Math.abs(nv - ov) < threshold) {
        current.value = nv
        return
      }
      if (rafId !== null) cancelAnimationFrame(rafId)
      startVal = current.value      // продолжаем от текущей (если предыдущая ещё крутилась)
      endVal = nv
      startTime = performance.now()
      rafId = requestAnimationFrame(frame)
    },
    { immediate: true }
  )

  return current
}