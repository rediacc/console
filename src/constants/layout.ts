/**
 * Shared layout constants for consistent UI sizing across the application
 */

export const DETAIL_PANEL = {
  /** Width of the panel when collapsed (showing only toggle button and icon) */
  COLLAPSED_WIDTH: 50,

  /** Minimum width of the expanded panel */
  MIN_WIDTH: 300,

  /** Maximum width of the expanded panel */
  MAX_WIDTH: 700,

  /** Default width as a percentage of viewport width (0.33 = 33%) */
  DEFAULT_WIDTH_PERCENTAGE: 0.33,

  /** Duration of fade in/out animations in milliseconds */
  ANIMATION_DURATION: 250,
} as const
