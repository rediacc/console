import { CSSProperties } from 'react'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const PANEL_CONTENT_PADDING = DESIGN_TOKENS.SPACING.PAGE_CARD_PADDING
const PANEL_HEADER_PADDING_Y = DESIGN_TOKENS.SPACING['1.5']
const PANEL_HEADER_PADDING_X = DESIGN_TOKENS.SPACING.PAGE_CARD_PADDING

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
  theme: _theme
}: PanelWrapperStylesParams): CSSProperties => {
  const backgroundColor = 'var(--color-bg-primary)'

  if (splitView) {
    return {
      width: '100%',
      height: '100%',
      backgroundColor,
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
    backgroundColor,
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
export const getStickyHeaderStyles = (_theme: 'light' | 'dark'): CSSProperties => ({
  padding: `${PANEL_HEADER_PADDING_Y}px ${PANEL_HEADER_PADDING_X}px`,
  borderBottom: '1px solid var(--color-border-secondary)',
  position: 'sticky',
  top: 0,
  backgroundColor: 'var(--color-bg-primary)',
  zIndex: 10,
})

/**
 * Returns the content wrapper styles for detail panels
 */
export const getContentWrapperStyles = (): CSSProperties => ({
  padding: `${PANEL_CONTENT_PADDING}px`,
})
