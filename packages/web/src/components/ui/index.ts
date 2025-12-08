/**
 * UI Components - Barrel Export
 *
 * Centralized export for all styled UI components.
 * These are reusable building blocks for page layouts.
 *
 * Usage:
 *   import { PageWrapper, CardHeader, ListTitle } from '@/components/ui'
 *
 * Or specific imports:
 *   import { PageWrapper } from '@/components/ui/page'
 */

// Page structure
export * from './Page';

// Form inputs and layout
export * from './Form';
export * from './Form/layout';

// Text components
// (legacy lowercase text.tsx now re-exports from Text/index to avoid case issues)

// Danger zone components
export * from './Danger';

// Utility components
export * from './Utils';

// Button component
export * from './Button';

// Tag component
export * from './Tag';

// Text component (unified)
export * from './Text';

// Rediacc unified components
export * from './Card';
export * from './Alert';
export * from './Stack';
export * from './Badge';
export * from './Divider';
export * from './Empty';
export * from './Modal';
export * from './Tabs';
export * from './Progress';
export * from './List';
