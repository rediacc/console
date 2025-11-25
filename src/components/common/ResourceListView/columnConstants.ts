/**
 * Shared column width standards for resource list pages.
 * Use these constants to keep all tables visually consistent.
 */
export const COLUMN_WIDTHS = {
  NAME: 150, // Primary identifiers (team, repository, storage names)
  NAME_WIDE: 200, // For identifiers that need extra space
  COUNT: 100, // Compact count/badge columns
  COUNT_WIDE: 120, // Counts that need slightly more room
  STATS_MOBILE: 140, // Mobile-only combined stats column
  TAG: 150, // Tag/category columns (team tags, statuses)
  VERSION: 120, // Vault/version numbers
  ACTIONS: 160, // Three-button action groups
  ACTIONS_WIDE: 200, // Wider action sections (4+ buttons)
} as const

type ResponsiveBreakpoint = 'xxl' | 'xl' | 'lg' | 'md' | 'sm' | 'xs'

/**
 * Convenience responsive breakpoints for column definitions.
 * Mobile combines data (xs); desktop splits data (sm and above).
 */
export const COLUMN_RESPONSIVE: Record<
  'MOBILE_ONLY' | 'DESKTOP_ONLY',
  ResponsiveBreakpoint[]
> = {
  MOBILE_ONLY: ['xs'],
  DESKTOP_ONLY: ['sm'],
}

export type ColumnWidthKey = keyof typeof COLUMN_WIDTHS
