import { CSSProperties } from 'react'

/**
 * Shared styling utilities for detail panels (Machine, Repository, Container)
 */

interface PanelWrapperStylesParams {
  splitView: boolean
  visible: boolean
  theme: 'light' | 'dark'
}

/**
 * Returns the wrapper styles for detail panels
 * Handles both splitView mode and standalone fixed positioning
 */
export const getPanelWrapperStyles = ({
  splitView,
  visible,
  theme
}: PanelWrapperStylesParams): CSSProperties => {
  if (splitView) {
    return {
      width: '100%',
      height: '100%',
      backgroundColor: theme === 'dark' ? '#141414' : '#fff',
      overflowY: 'auto',
      overflowX: 'hidden',
    }
  }

  return {
    position: 'fixed',
    top: 0,
    right: visible ? 0 : '-520px',
    bottom: 0,
    width: '520px',
    maxWidth: '100vw',
    backgroundColor: theme === 'dark' ? '#141414' : '#fff',
    boxShadow: '-2px 0 8px rgba(0, 0, 0, 0.15)',
    zIndex: 1000,
    transition: 'right 0.3s ease-in-out',
    overflowY: 'auto',
    overflowX: 'hidden',
  }
}

/**
 * Returns the sticky header styles for detail panels
 */
export const getStickyHeaderStyles = (theme: 'light' | 'dark'): CSSProperties => ({
  padding: '16px 24px',
  borderBottom: `1px solid ${theme === 'dark' ? '#303030' : '#f0f0f0'}`,
  position: 'sticky',
  top: 0,
  backgroundColor: theme === 'dark' ? '#141414' : '#fff',
  zIndex: 10,
})

/**
 * Returns the content wrapper styles for detail panels
 */
export const getContentWrapperStyles = (): CSSProperties => ({
  padding: '24px',
})
