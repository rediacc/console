/**
 * Centralized styles for detail panels (Machine, Repo, Container)
 * Ensures consistent typography and layout across all panels
 */

import { CSSProperties } from 'react'

/**
 * Typography styles for detail panel text elements
 */
export const DETAIL_PANEL_TEXT = {
  // Label text (left side, secondary)
  label: {
    fontSize: 12,
  } as CSSProperties,

  // Value text (right side, regular)
  value: {
    fontSize: 13,
  } as CSSProperties,

  // Value text (emphasized/important)
  valueStrong: {
    fontSize: 13,
    fontWeight: 600,
  } as CSSProperties,

  // Monospace text (IDs, paths, code)
  monospace: {
    fontSize: 12,
    fontFamily: 'monospace',
  } as CSSProperties,

  // Secondary metadata text (timestamps, etc)
  secondary: {
    fontSize: 11,
  } as CSSProperties,
} as const

/**
 * Layout styles for detail panel containers
 */
export const DETAIL_PANEL_LAYOUT = {
  // Inline field row (label left, value right)
  inlineField: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  } as CSSProperties,

  // Vertical field (label top, value bottom with br)
  verticalField: {
    display: 'block',
  } as CSSProperties,
} as const

/**
 * Icon sizes for detail panels
 */
export const DETAIL_PANEL_ICONS = {
  header: { fontSize: 24 },      // Panel header icon
  section: { fontSize: 20 },      // First section header
  divider: { fontSize: 16 },      // Divider section icons
  inline: { fontSize: 14 },       // Inline field icons
} as const

/**
 * Combined style presets for common patterns
 */
export const DETAIL_PANEL_PRESETS = {
  // Label + value inline
  labelValueInline: {
    container: DETAIL_PANEL_LAYOUT.inlineField,
    label: DETAIL_PANEL_TEXT.label,
    value: DETAIL_PANEL_TEXT.value,
  },

  // Label + strong value inline
  labelValueStrongInline: {
    container: DETAIL_PANEL_LAYOUT.inlineField,
    label: DETAIL_PANEL_TEXT.label,
    value: DETAIL_PANEL_TEXT.valueStrong,
  },

  // Label + monospace value inline
  labelMonospaceInline: {
    container: DETAIL_PANEL_LAYOUT.inlineField,
    label: DETAIL_PANEL_TEXT.label,
    value: DETAIL_PANEL_TEXT.monospace,
  },
} as const
