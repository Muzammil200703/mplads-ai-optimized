import { useEffect, useRef, useState } from "react"

/** Animates a number counting up from 0 to its target value on mount. */
export default function CountUp({ value, duration = 1000, formatter }) {
  const [display, setDisplay] = useState(0)
  const startRef = useRef(null)
  const fromRef = useRef(0)

  useEffect(() => {
    fromRef.current = 0
    startRef.current = null
    let raf

    function step(timestamp) {
      if (!startRef.current) startRef.current = timestamp
      const progress = Math.min((timestamp - startRef.current) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      const current = Math.round(fromRef.current + (value - fromRef.current) * eased)
      setDisplay(current)
      if (progress < 1) {
        raf = requestAnimationFrame(step)
      }
    }

    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  const shown = formatter ? formatter(display) : display.toLocaleString("en-IN")
  return <>{shown}</>
}
