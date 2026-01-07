/**
 * Column constants to avoid circular dependencies
 * Import from this file in factories, and re-export from index.tsx for external consumers
 */

import type { Breakpoint } from 'antd';

/**
 * Responsive breakpoints to hide columns on mobile (xs).
 * Use this constant for columns that should only show on sm screens and larger.
 */
export const RESPONSIVE_HIDE_XS: Breakpoint[] = ['sm', 'md', 'lg', 'xl', 'xxl'] as const;
