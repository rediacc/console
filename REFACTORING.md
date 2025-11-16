# Component Refactoring Guide

This document provides comprehensive guidelines for refactoring components in the console application. It captures the patterns established in PR #163 and should be used as a reference for all future component refactoring work.

---

## Table of Contents

1. [When to Refactor](#when-to-refactor)
2. [Component Structure Migration](#component-structure-migration)
3. [File Splitting Patterns](#file-splitting-patterns)
4. [Table Data Extraction](#table-data-extraction)
5. [UI Primitives Creation](#ui-primitives-creation)
6. [Mobile Responsive Patterns](#mobile-responsive-patterns)
7. [Color System Migration](#color-system-migration)
8. [Step-by-Step Refactoring Process](#step-by-step-refactoring-process)
9. [Common Pitfalls](#common-pitfalls)
10. [Verification Checklist](#verification-checklist)

---

## When to Refactor

Refactor a component when it meets **any** of these criteria:

### Size Thresholds
- ✅ Component file exceeds **300 lines**
- ✅ Component has multiple distinct responsibilities
- ✅ Styles are inline or in a separate CSS file (not styled-components)
- ✅ Component contains hard-coded table column configurations

### Quality Indicators
- ✅ Component uses old color variables (`color-primary-bg`, `color-primary`)
- ✅ Component has poor mobile responsiveness
- ✅ Component structure makes it hard to maintain or test
- ✅ Component is in the old folder structure (`src/components/layouts/`)

---

## Component Structure Migration

### Old Structure (Flat Files)
```
src/components/layouts/
├── AuthLayout.tsx      # 51 lines - simple component
└── MainLayout.tsx      # 886 lines - complex component
```

### New Structure (Modular Folders)

#### Simple Components (< 100 lines)
For small components, use a folder with just `index.tsx` and `styles.ts`:

```
src/components/layout/
└── AuthLayout/
    ├── index.tsx       # Main component
    └── styles.ts       # Styled components
```

#### Complex Components (> 300 lines)
For large components, split into logical modules:

```
src/components/layout/
└── MainLayout/
    ├── index.tsx           # Main component (249 lines)
    ├── styles.ts           # Styled components (124 lines)
    ├── types.ts            # Type definitions (22 lines)
    ├── helpers.ts          # Helper functions (97 lines)
    ├── menuItems.tsx       # Menu configuration (145 lines)
    ├── Sidebar/            # Sub-component
    │   ├── index.tsx       # (176 lines)
    │   └── styles.ts       # (149 lines)
    └── UserMenu/           # Sub-component
        ├── index.tsx       # (135 lines)
        └── styles.ts       # (99 lines)
```

**Result**: 886 lines split into 9 files, each under 250 lines!

### Folder Naming Rules

| Type | Case | Example | ❌ Wrong |
|------|------|---------|----------|
| **Category folders** | lowercase | `layout/`, `ui/`, `common/` | `Layout/`, `UI/` |
| **Component folders** | PascalCase | `MainLayout/`, `ResourceListView/` | `main-layout/`, `mainLayout/` |
| **Component files** | PascalCase | `MainLayout.tsx`, `AuthLayout.tsx` | `main-layout.tsx` |
| **Helper files** | camelCase | `menuItems.tsx`, `helpers.ts`, `utils.ts` | `menu-items.tsx`, `MenuItems.tsx` |
| **Type files** | camelCase | `types.ts`, `interfaces.ts` | `Types.ts`, `Interfaces.ts` |
| **Data files** | camelCase | `data.tsx`, `columns.tsx` | `Data.tsx`, `Columns.tsx` |

**NEVER use kebab-case** (e.g., ❌ `menu-items.tsx`, ❌ `user-utils.ts`)

---

## File Splitting Patterns

### 1. Extract Types

**Before** (in component file):
```tsx
// MainLayout.tsx (line 50-70)
interface MenuItem {
  key: string
  icon: React.ReactNode
  label: string
  children?: MenuItem[]
  'data-testid'?: string
}

const SIDEBAR_EXPANDED_WIDTH = 240
const SIDEBAR_COLLAPSED_WIDTH = 80
```

**After** (in separate file):
```tsx
// types.ts
export interface MenuItem {
  key: string
  icon: React.ReactNode
  label: string
  children?: MenuItem[]
  'data-testid'?: string
}

export const SIDEBAR_EXPANDED_WIDTH = 240
export const SIDEBAR_COLLAPSED_WIDTH = 80
```

### 2. Extract Helper Functions

**Before** (in component file):
```tsx
// MainLayout.tsx (line 200-300)
const buildMenuItems = (items: MenuItem[], uiMode: string) => {
  // 50 lines of logic
}

const flattenMenuRoutes = (items: MenuItem[]): string[] => {
  // 30 lines of logic
}
```

**After** (in separate file):
```tsx
// helpers.ts
import type { MenuItem } from './types'

export const buildMenuItems = (
  items: MenuItem[],
  uiMode: string
): MenuItem[] => {
  // 50 lines of logic
}

export const flattenMenuRoutes = (
  items: MenuItem[]
): string[] => {
  // 30 lines of logic
}
```

### 3. Extract Configuration

**Before** (in component file):
```tsx
// MainLayout.tsx (line 100-200)
const menuItems = [
  {
    key: '/dashboard',
    icon: <DashboardOutlined />,
    label: t('navigation.dashboard'),
    // ... 100+ lines of menu configuration
  }
]
```

**After** (in separate file):
```tsx
// menuItems.tsx
import type { TFunction } from 'i18next'
import type { MenuItem } from './types'

export const getMenuItems = (t: TFunction): MenuItem[] => [
  {
    key: '/dashboard',
    icon: <DashboardOutlined />,
    label: t('navigation.dashboard'),
    // ... configuration
  }
]
```

### 4. Extract Sub-Components

**When to Extract**:
- Sub-component is **> 50 lines**
- Sub-component has its own state or logic
- Sub-component is used only by this parent

**Example**:
```tsx
// MainLayout/Sidebar/index.tsx
export const Sidebar: React.FC<SidebarProps> = ({ ... }) => {
  // Sidebar logic and JSX
}

// MainLayout/Sidebar/styles.ts
export const StyledSider = styled(Sider)...
export const MenuScrollArea = styled.div...
```

---

## Table Data Extraction

### Pattern: Separate Table Columns from Component Logic

**Before** (in page component):
```tsx
// TeamsPage.tsx (400 lines)
const TeamsPage: React.FC = () => {
  const { t } = useTranslation('system')

  const columns = [
    {
      title: t('tables.teams.teamName'),
      dataIndex: 'teamName',
      key: 'teamName',
      render: (text: string) => (
        <Space>
          <TeamOutlined />
          <strong>{text}</strong>
        </Space>
      ),
    },
    // ... 100+ lines of column definitions
  ]

  return (
    <Table columns={columns} ... />
  )
}
```

**After** (split into two files):

```tsx
// data.tsx (173 lines)
import type { TableProps } from 'antd'
import type { Team } from '@/api/queries/teams'
import type { TFunction } from 'i18next'

interface GetTeamColumnsParams {
  tSystem: TFunction<'system'>
  tCommon: TFunction<'common'>
  onEdit: (team: Team) => void
  onDelete: (teamName: string) => void
  isDeleting: boolean
}

export const getTeamColumns = ({
  tSystem,
  tCommon,
  onEdit,
  onDelete,
  isDeleting,
}: GetTeamColumnsParams): TableProps<Team>['columns'] => [
  {
    title: tSystem('tables.teams.teamName'),
    dataIndex: 'teamName',
    key: 'teamName',
    render: (text: string) => (
      <Space>
        <TeamOutlined />
        <strong>{text}</strong>
      </Space>
    ),
  },
  // ... all column definitions
]
```

```tsx
// TeamsPage.tsx (reduced to 225 lines)
import { getTeamColumns } from './data'

const TeamsPage: React.FC = () => {
  const { t: tSystem } = useTranslation('system')
  const { t: tCommon } = useTranslation('common')

  const columns = useMemo(
    () => getTeamColumns({
      tSystem,
      tCommon,
      onEdit: handleEdit,
      onDelete: handleDelete,
      isDeleting,
    }),
    [tSystem, tCommon, isDeleting]
  )

  return (
    <Table columns={columns} ... />
  )
}
```

**Benefits**:
- ✅ Cleaner component logic
- ✅ Easier to test table configurations
- ✅ Better code organization
- ✅ Reusable column definitions

---

## UI Primitives Creation

### Identify Reusable Patterns

When refactoring, look for **repeated UI patterns** across components:

#### Common Patterns to Extract

1. **Page Structure**
```tsx
// ❌ Repeated in multiple pages
<Card>
  <div style={{ marginBottom: 24 }}>
    <h2>{title}</h2>
  </div>
  <div>{children}</div>
</Card>

// ✅ Extract to ui/page.tsx
export const PageWrapper = styled.div`...`
export const SectionHeading = styled.h2`...`
```

2. **Card Headers**
```tsx
// ❌ Repeated pattern
<div style={{ display: 'flex', justifyContent: 'space-between' }}>
  <h3>{title}</h3>
  <Button>{action}</Button>
</div>

// ✅ Extract to ui/card.tsx
export const CardHeader = styled.div`...`
export const CardTitle = styled.h3`...`
```

3. **List Items**
```tsx
// ✅ Extract to ui/list.tsx
export const ListItem = styled.div`...`
export const ListTitle = styled.span`...`
export const ListMeta = styled.div`...`
```

### UI Component Organization

```
src/components/ui/
├── index.ts           # Barrel export (all components)
├── page.tsx           # PageWrapper, SectionStack, SectionHeading
├── card.tsx           # Card-related styled components
├── list.tsx           # List-related styled components
├── modal.tsx          # Modal layout components
├── form.tsx           # Form layout components
├── text.tsx           # Text variants (Muted, Strong, etc.)
├── danger.tsx         # Danger zone components
└── utils.tsx          # Utility components (Divider, Spacer, etc.)
```

### UI Barrel Export Pattern

```tsx
// ui/index.ts
/**
 * UI Components - Barrel Export
 *
 * Centralized export for all styled UI components.
 * These are reusable building blocks for page layouts.
 *
 * Usage:
 *   import { PageWrapper, CardHeader, ListTitle } from '@/components/ui'
 */

// Page structure
export * from './page'

// Card components
export * from './card'

// List components
export * from './list'

// ... etc
```

---

## Mobile Responsive Patterns

### Pattern 1: Mobile Drawer Navigation

**For components with sidebar navigation**, replace fixed sidebar with a drawer on mobile:

```tsx
// MainLayout/index.tsx
const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

const handleSidebarToggle = () => {
  // Toggle drawer on mobile, collapse sidebar on desktop
  const isMobile = window.innerWidth <= 768
  if (isMobile) {
    setMobileMenuOpen(prev => !prev)
  } else {
    setCollapsed(prev => !prev)
  }
}

return (
  <>
    {/* Desktop Sidebar */}
    <Sidebar collapsed={collapsed} />

    {/* Mobile Drawer */}
    <Drawer
      placement="left"
      onClose={() => setMobileMenuOpen(false)}
      open={mobileMenuOpen}
      width={SIDEBAR_EXPANDED_WIDTH}
    >
      <Sidebar $isDrawer />
    </Drawer>
  </>
)
```

**Styled component**:
```tsx
// Sidebar/styles.ts
export const StyledSider = styled(Sider)<{ $isDrawer?: boolean }>`
  /* Hide sidebar on mobile - use drawer only */
  @media (max-width: 768px) {
    display: ${({ $isDrawer }) => ($isDrawer ? 'block' : 'none')};
  }
`
```

### Pattern 2: Responsive Table Columns

**For tables with many columns**, combine columns on mobile:

```tsx
// data.tsx
export const getColumns = (): TableProps['columns'] => {
  const columns = [
    // Combined Stats column for mobile (show only on xs, hide on sm)
    {
      title: 'Stats',
      key: 'stats',
      responsive: ['xs'],
      render: (_, record) => (
        <Space direction="vertical" size={4}>
          <Badge count={record.memberCount} />
          <Badge count={record.machineCount} />
        </Space>
      ),
    },
    // Separate columns for desktop (show on sm and above)
    {
      title: 'Members',
      dataIndex: 'memberCount',
      responsive: ['sm'],
      render: (count) => <Badge count={count} />,
    },
    {
      title: 'Machines',
      dataIndex: 'machineCount',
      responsive: ['sm'],
      render: (count) => <Badge count={count} />,
    },
  ]

  return columns
}
```

### Pattern 3: Touch-Optimized Scrolling

```tsx
// ResourceListView/styles.ts
export const TableWrapper = styled.div`
  /* Better scroll experience on mobile devices */
  @media (max-width: 576px) {
    -webkit-overflow-scrolling: touch;

    .ant-table-wrapper {
      overflow-x: auto;
    }

    .ant-table-pagination {
      flex-wrap: wrap;
      justify-content: center;
      gap: ${({ theme }) => theme.spacing.SM}px;
    }
  }
`
```

### Pattern 4: Responsive Layout Stacking

```tsx
// styles.ts
export const HeaderRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
  }
`
```

---

## Color System Migration

### Old vs New Color Variables

When refactoring, update color variables to match the grayscale palette:

| Old Variable | New Variable | Usage |
|--------------|--------------|-------|
| `var(--color-primary-bg)` | `var(--color-bg-selected)` | Selected/active item background |
| `var(--color-primary)` | `var(--color-text-selected)` | Selected/active item text |
| `var(--color-primary)` | `var(--color-primary)` | Buttons, badges (keep primary) |

### Selection State Pattern

**Before**:
```tsx
export const MenuItem = styled.div<{ $isActive: boolean }>`
  background-color: ${({ $isActive }) =>
    $isActive ? 'var(--color-primary-bg)' : 'transparent'};
  color: ${({ $isActive }) =>
    $isActive ? 'var(--color-primary)' : 'var(--color-text-primary)'};
`
```

**After**:
```tsx
export const MenuItem = styled.div<{ $isActive: boolean }>`
  background-color: ${({ $isActive }) =>
    $isActive ? 'var(--color-bg-selected)' : 'transparent'};
  color: ${({ $isActive }) =>
    $isActive ? 'var(--color-text-selected)' : 'var(--color-text-primary)'};
`
```

### When to Keep Primary Colors

Keep `var(--color-primary)` for:
- ✅ Primary buttons
- ✅ Badges and tags
- ✅ Icons that need emphasis
- ✅ Links and CTAs

Use `var(--color-text-selected)` for:
- ✅ Selected menu items
- ✅ Active navigation items
- ✅ Selected table rows
- ✅ Active tabs

---

## Step-by-Step Refactoring Process

### Phase 1: Analysis (Before Writing Code)

1. **Measure the component**
   ```bash
   wc -l src/components/ComponentName.tsx
   # If > 300 lines, proceed with refactoring
   ```

2. **Identify logical sections**
   - Types and interfaces
   - Constants and configuration
   - Helper functions
   - Sub-components
   - Main component logic

3. **Check for table configurations**
   - Are there column definitions?
   - Can they be extracted to `data.tsx`?

4. **Check for mobile responsiveness**
   - Does it work on mobile?
   - Are there responsive patterns to add?

### Phase 2: Structure Setup

1. **Create folder structure**
   ```bash
   mkdir -p src/components/category/ComponentName
   cd src/components/category/ComponentName
   touch index.tsx styles.ts
   ```

2. **For complex components, add more files**
   ```bash
   touch types.ts helpers.ts data.tsx
   mkdir SubComponent1 SubComponent2
   ```

### Phase 3: File Migration

1. **Move types** to `types.ts`
   - Export all interfaces and type aliases
   - Export constants

2. **Move helpers** to `helpers.ts`
   - Export utility functions
   - Keep business logic with component

3. **Move configuration** to dedicated files
   - `menuItems.tsx` for menu configs
   - `data.tsx` for table columns

4. **Move styles** to `styles.ts`
   - Convert inline styles to styled-components
   - Update color variables
   - Add responsive breakpoints

5. **Create sub-components** if needed
   - Extract large sections (> 50 lines)
   - Create `SubComponent/index.tsx` and `SubComponent/styles.ts`

### Phase 4: Main Component Cleanup

1. **Update imports**
   ```tsx
   import { MenuItem } from './types'
   import { buildMenuItems } from './helpers'
   import { getMenuItems } from './menuItems'
   import { Sidebar } from './Sidebar'
   import { UserMenu } from './UserMenu'
   import { StyledHeader, Logo } from './styles'
   ```

2. **Remove old code**
   - Delete moved types
   - Delete moved helpers
   - Delete inline styles

3. **Verify component still works**

### Phase 5: Mobile Responsiveness

1. **Add mobile breakpoints** to styles
   ```tsx
   @media (max-width: 768px) {
     // Mobile styles
   }
   ```

2. **Add responsive table columns** if applicable

3. **Add mobile drawer** for navigation if applicable

### Phase 6: Color System Update

1. **Find and replace** old color variables
   ```bash
   grep -r "color-primary-bg" .
   grep -r "color-primary[^-]" .
   ```

2. **Update to new variables** based on usage context

### Phase 7: Testing & Verification

1. **Run build**
   ```bash
   npm run build
   ```

2. **Check TypeScript errors**
   ```bash
   npm run type-check
   ```

3. **Test in browser**
   - Desktop view
   - Mobile view (< 768px)
   - Tablet view (768px - 1024px)
   - Light theme
   - Dark theme

---

## Common Pitfalls

### ❌ Pitfall 1: Not Using Transient Props

**Wrong**:
```tsx
export const MenuItem = styled.div<{ isActive: boolean }>`
  // ❌ 'isActive' will leak to DOM and cause React warning
  background: ${({ isActive }) => isActive ? 'red' : 'blue'};
`
```

**Correct**:
```tsx
export const MenuItem = styled.div<{ $isActive: boolean }>`
  // ✅ '$isActive' won't leak to DOM
  background: ${({ $isActive }) => $isActive ? 'red' : 'blue'};
`
```

### ❌ Pitfall 2: Breaking Import Paths

**Wrong**:
```tsx
// Old location: src/components/layouts/MainLayout.tsx
// New location: src/components/layout/MainLayout/index.tsx

// Other files still importing from old path
import MainLayout from '@/components/layouts/MainLayout'  // ❌ Broken!
```

**Correct**:
```tsx
// Update ALL imports
import MainLayout from '@/components/layout/MainLayout'  // ✅
```

### ❌ Pitfall 3: Forgetting Mobile Testing

Always test on mobile viewports:
- 375px (iPhone SE)
- 768px (iPad)
- 1024px (Desktop)

### ❌ Pitfall 4: Not Extracting Configuration

**Wrong**:
```tsx
// Keeping 200 lines of column definitions in component
const columns = [ /* 200 lines */ ]
```

**Correct**:
```tsx
// Extract to data.tsx
import { getColumns } from './data'
const columns = getColumns(...)
```

### ❌ Pitfall 5: Using Wrong Color Variables

**Wrong**:
```tsx
// Using primary color for selection states
background: var(--color-primary-bg)  // ❌ Old pattern
```

**Correct**:
```tsx
// Using selection colors for selection states
background: var(--color-bg-selected)  // ✅ New pattern
```

---

## Verification Checklist

Before submitting a PR, verify:

### Structure
- [ ] Component is in the correct folder (`layout/`, `common/`, `ui/`)
- [ ] Folder name uses PascalCase (matches component name)
- [ ] Helper files use camelCase
- [ ] No kebab-case filenames
- [ ] Each file is under 300 lines

### Files
- [ ] Main component in `index.tsx`
- [ ] Styles in `styles.ts`
- [ ] Types in `types.ts` (if needed)
- [ ] Helpers in `helpers.ts` (if needed)
- [ ] Table data in `data.tsx` (if applicable)
- [ ] Sub-components in separate folders

### Styling
- [ ] All styles use styled-components (no inline styles)
- [ ] Transient props prefixed with `$`
- [ ] Color variables updated to new system
- [ ] Responsive breakpoints added
- [ ] No hard-coded colors or spacing

### Mobile
- [ ] Component tested on mobile (< 768px)
- [ ] Tables are scrollable on mobile
- [ ] Navigation works on mobile
- [ ] Touch targets are adequate (min 44px)

### Testing
- [ ] Build succeeds (`npm run build`)
- [ ] No TypeScript errors
- [ ] Works in light theme
- [ ] Works in dark theme
- [ ] No console errors
- [ ] All imports updated

### Documentation
- [ ] Complex logic has comments
- [ ] Exported functions have JSDoc (if applicable)
- [ ] README updated (if applicable)

---

## Examples from PR #163

### Example 1: MainLayout Refactoring

**Before**: Single file with 886 lines
**After**: 9 files, each under 250 lines

**Files created**:
- `MainLayout/index.tsx` - Main component (249 lines)
- `MainLayout/styles.ts` - Styled components (124 lines)
- `MainLayout/types.ts` - Type definitions (22 lines)
- `MainLayout/helpers.ts` - Utility functions (97 lines)
- `MainLayout/menuItems.tsx` - Menu configuration (145 lines)
- `MainLayout/Sidebar/index.tsx` - Sidebar component (176 lines)
- `MainLayout/Sidebar/styles.ts` - Sidebar styles (149 lines)
- `MainLayout/UserMenu/index.tsx` - User menu component (135 lines)
- `MainLayout/UserMenu/styles.ts` - User menu styles (99 lines)

### Example 2: TeamsPage Refactoring

**Before**: Single file with 400+ lines (with table columns)
**After**: 2 files

**Changes**:
- `TeamsPage.tsx` - Reduced to 225 lines (logic only)
- `data.tsx` - Created with 173 lines (table columns)

### Example 3: Sidebar Color Migration

**Changes made**:
- Updated 11 instances of `color-primary-bg` → `color-bg-selected`
- Updated 7 instances of `color-primary` → `color-text-selected`
- Affected components: MenuItem, MenuIcon, MenuLabel, TooltipItem, SubMenuItem

---

## Quick Reference

### File Naming Cheat Sheet

```
✅ CORRECT                    ❌ WRONG
src/components/layout/       src/components/Layout/
MainLayout/                  main-layout/
  index.tsx                    MainLayout.tsx (in folder)
  styles.ts                    Styles.ts
  types.ts                     Types.ts
  helpers.ts                   Helpers.ts
  menuItems.tsx                menu-items.tsx
  data.tsx                     Data.tsx
```

### Import Pattern Cheat Sheet

```tsx
// ✅ Internal imports (same component)
import { MenuItem } from './types'
import { buildMenu } from './helpers'
import { Sidebar } from './Sidebar'

// ✅ UI primitives
import { PageWrapper, CardHeader } from '@/components/ui'

// ✅ Absolute imports
import { useTheme } from '@/context/ThemeContext'
```

### Color Variable Cheat Sheet

```tsx
// Selection/Active States
background: var(--color-bg-selected)
color: var(--color-text-selected)

// Buttons/Badges/Emphasis
background: var(--color-primary)
color: var(--color-primary)

// Hover States
background: var(--color-bg-hover)
background: var(--color-bg-tertiary)
```

---

## Getting Help

When refactoring:
1. **Reference STYLE.md** for styling guidelines
2. **Reference this document** for structure guidelines
3. **Look at PR #163** for real examples
4. **Ask for review** before opening PR if unsure

---

**Last Updated**: November 2025 (PR #163)
**Maintainer**: Architecture Team
**Related Docs**: STYLE.md, CLAUDE.md
