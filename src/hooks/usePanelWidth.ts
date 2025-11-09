import { useState, useEffect } from 'react'

/**
 * Custom hook to calculate and maintain responsive panel width for detail panels
 *
 * @returns Panel width in pixels (33% of window width, min 300px, max 700px)
 *
 * @example
 * const splitWidth = usePanelWidth()
 */
export const usePanelWidth = (): number => {
  const calculatePanelWidth = () => {
    const windowWidth = window.innerWidth
    const panelWidth = Math.floor(windowWidth * 0.33)
    // Ensure minimum width of 300px and maximum of 700px
    return Math.max(300, Math.min(700, panelWidth))
  }

  const [panelWidth, setPanelWidth] = useState(calculatePanelWidth)

  useEffect(() => {
    const handleResize = () => {
      setPanelWidth(calculatePanelWidth())
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  return panelWidth
}
