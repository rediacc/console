# UI Component Consolidation - Big Bang Refactor

## Context

The codebase has accumulated significant UI variant bloat. Analysis revealed:
- **TextVariant**: 10 variants defined, only 2 used (caption, muted)
- **TagVariant**: 16 options (8 variants + 8 presets), 6 unused, 4 duplicate colors
- **ButtonVariant**: `danger` variant never used, `lg` size never used
- **InputVariant**: `search`, `code`, `secret` variants never used
- **primitives.ts**: 107 styled components, 12 completely unused, many duplicate RediaccX functionality

## Goals

1. Reduce cognitive load by eliminating unused/duplicate variants
2. Consolidate primitives.ts text/tag components into RediaccText/RediaccTag
3. Simplify component APIs while maintaining flexibility via props
4. Delete dead code

---

## Phase 1: Delete Unused Exports from primitives.ts

**File**: `/packages/web/src/styles/primitives.ts`

Delete these completely unused exports (0 references in codebase):

```
NoMarginTitle
FeatureCard
SpacedCard
ContentSection
CenteredRow
InputSlot
CenteredFooter
SectionMargin
InfoList
FilterRangePicker
FilterCheckbox
pulseAnimation
```

Also remove the `fullWidthControlStyles` CSS helper if no longer needed after cleanup.

---

## Phase 2: Consolidate RediaccText Variants

**Files**:
- `/packages/web/src/components/ui/Text/RediaccText.types.ts`
- `/packages/web/src/components/ui/Text/RediaccText.styles.ts`
- `/packages/web/src/components/ui/Text/RediaccText.tsx`

### Current → New Mapping

**KEEP these variants (4):**
| Variant | Purpose |
|---------|---------|
| `body` | Default text (BASE size, REGULAR weight, primary color) |
| `caption` | Small secondary text (CAPTION size, secondary color) |
| `title` | Headings (H4 size, SEMIBOLD weight, primary color) |
| `mono` | Code/monospace text |

**REMOVE these variants (6):**
| Variant | Migration Path |
|---------|----------------|
| `subtitle` | Use `variant="title" size="lg" weight="medium"` |
| `helper` | Use `variant="caption"` (identical purpose) |
| `label` | Use `variant="body" size="sm" weight="medium"` |
| `muted` | Use `variant="caption" size="xs"` |
| `danger` | Use `variant="body" color="danger"` |
| `description` | Use `variant="caption"` with custom lineHeight if needed |

### Implementation

1. Update `TextVariant` type to only include: `'body' | 'caption' | 'title' | 'mono'`

2. Update `resolveTextVariantTokens` switch statement to only handle 4 cases

3. Search codebase for any usage of removed variants and migrate:
   - `variant="subtitle"` → `variant="title" size="lg" weight="medium"`
   - `variant="helper"` → `variant="caption"`
   - `variant="label"` → `variant="body" size="sm" weight="medium"`
   - `variant="muted"` → `variant="caption" size="xs"`
   - `variant="danger"` → `variant="body" color="danger"`
   - `variant="description"` → `variant="caption"`

---

## Phase 3: Consolidate RediaccTag Variants

**Files**:
- `/packages/web/src/components/ui/Tag/RediaccTag.types.ts`
- `/packages/web/src/components/ui/Tag/RediaccTag.styles.ts`
- `/packages/web/src/components/ui/Tag/RediaccTag.tsx`

### Current → New Mapping

**KEEP these core variants (6):**
| Variant | Color |
|---------|-------|
| `default` | neutral/gray |
| `success` | green |
| `warning` | orange |
| `error` | red |
| `info` | cyan/blue |
| `neutral` | gray |

**KEEP these domain presets (3):**
| Preset | Maps To | Purpose |
|--------|---------|---------|
| `team` | success (green) | Team identifiers |
| `machine` | primary (blue) | Machine/server refs |
| `region` | info (cyan) | Region identifiers |

**REMOVE these (7):**
| Item | Reason |
|------|--------|
| `primary` variant | Use `machine` preset or `info` |
| `secondary` variant | Use `neutral` |
| `cluster` preset | 0 usages |
| `pool` preset | 0 usages |
| `bridge` preset | Merge into `machine` (same color) |
| `vault` preset | 0 usages |
| `status` preset | 0 usages |

### Implementation

1. Update `TagVariant` type: `'default' | 'success' | 'warning' | 'error' | 'info' | 'neutral'`

2. Update `TagPreset` type: `'team' | 'machine' | 'region'`

3. Update `PRESET_VARIANT_MAP` to only include 3 presets

4. Search codebase and migrate:
   - `variant="primary"` → `variant="info"` or `preset="machine"`
   - `variant="secondary"` → `variant="neutral"`
   - `preset="bridge"` → `preset="machine"`
   - `preset="cluster"` → `preset="machine"` or `variant="info"`
   - `preset="pool"` → `variant="info"`
   - `preset="vault"` → `variant="neutral"`
   - `preset="status"` → `variant="default"`

---

## Phase 4: Simplify RediaccButton

**Files**:
- `/packages/web/src/components/ui/Button/RediaccButton.types.ts`
- `/packages/web/src/components/ui/Button/RediaccButton.styles.ts`
- `/packages/web/src/components/ui/Button/RediaccButton.tsx`

### Changes

1. **Remove `danger` variant** (0 usages)
   - Update `ButtonVariant` type: `'primary'` only (or keep as single default)
   - Remove danger styling from `resolveRediaccButtonVariantTokens`

2. **Remove `lg` size** (0 usages)
   - Update `ButtonSize` type: `'sm' | 'md'`
   - Remove lg case from `resolveRediaccButtonHeight`

3. Search codebase to ensure no usages exist (should be none per analysis)

---

## Phase 5: Simplify RediaccInput

**Files**:
- `/packages/web/src/components/ui/Form/Input/RediaccInput.types.ts`
- `/packages/web/src/components/ui/Form/Input/RediaccInput.styles.ts`
- `/packages/web/src/components/ui/Form/Input/RediaccInput.tsx`

### Changes

1. **Remove unused variants**
   - Update `InputVariant` type: `'default'` only
   - Remove `search`, `code`, `secret` from styling logic

2. **Remove `lg` size** (0 usages)
   - Update `InputSize` type: `'sm' | 'md'`
   - Remove lg case from size styling

3. Search codebase to ensure no usages exist

---

## Phase 6: Migrate primitives.ts Text Components → RediaccText

**Goal**: Replace legacy styled text components with RediaccText

### Migration Table

| Old Component | New Usage | Files to Update |
|---------------|-----------|-----------------|
| `CardTitle` | `<RediaccText variant="title">` | ~89 usages |
| `HelperText` | `<RediaccText variant="caption">` | ~40 usages |
| `CaptionText` | `<RediaccText variant="caption" size="xs">` | ~25 usages |
| `FormLabel` | `<RediaccText variant="body" size="sm" weight="medium">` | ~41 usages |
| `TitleText` | `<RediaccText variant="title" size={...}>` | ~35 usages |
| `SecondaryText` | `<RediaccText color="secondary">` | ~12 usages |
| `MonoText` | `<RediaccText variant="mono">` | ~22 usages |
| `ItalicText` | `<RediaccText style={{ fontStyle: 'italic' }} color="secondary">` | ~3 usages |

### Implementation Strategy

For each component:
1. Search all usages with grep
2. Replace JSX usage with RediaccText equivalent
3. Update imports (add RediaccText, remove old component)
4. After all migrations complete, delete from primitives.ts

**Note**: Some components like `CardTitle` are used as styled base in other files. Those need special handling - the styled component should extend RediaccText instead.

---

## Phase 7: Migrate primitives.ts Tag Components → RediaccTag

**Goal**: Replace legacy styled tag components with RediaccTag

### Migration Table

| Old Component | New Usage | Files to Update |
|---------------|-----------|-----------------|
| `StatusTag` | `<RediaccTag variant={...}>` with appropriate variant | ~39 usages |
| `PillTag` | `<RediaccTag size="sm">` | ~8 usages |
| `StatusBadge` | `<RediaccTag>` (styled inline) | ~7 usages |
| `StatusTagSmall` | `<RediaccTag size="sm">` | ~2 usages |

### Implementation Strategy

Same as text migration - search, replace, update imports, then delete.

---

## Phase 8: Clean Up primitives.ts Tag/Status Types

After Tag migration, these types in primitives.ts become redundant:

```typescript
// REMOVE these type definitions (now in RediaccTag.types.ts)
export type StatusVariant = ...
export type TagVariant = ...
export type TagSize = ...

// REMOVE these helper functions (now in RediaccTag.styles.ts)
const STATUS_TOKEN_KEYS = ...
const resolveStatusTokens = ...
const TAG_TOKEN_KEYS = ...
const resolveTagVariantTokens = ...
const resolveTagPadding = ...
const resolveTagRadius = ...
const resolveTagFontSize = ...
```

Update any files importing these types to import from `@/components/ui/Tag` instead.

---

## Parallel Execution Strategy

### Group A (Component Type Definitions) - Run First
- Task A1: Phase 2 - RediaccText variant consolidation
- Task A2: Phase 3 - RediaccTag variant consolidation
- Task A3: Phase 4 - RediaccButton simplification
- Task A4: Phase 5 - RediaccInput simplification

### Group B (Primitives Cleanup) - Run After Group A
- Task B1: Phase 1 - Delete unused primitives exports
- Task B2: Phase 6 - Migrate text components (split by directory)
  - B2a: pages/ceph/*
  - B2b: pages/settings/*, pages/organization/*
  - B2c: pages/dashboard/*, pages/queue/*
  - B2d: components/common/*
  - B2e: components/resources/*
  - B2f: components/layout/*
- Task B3: Phase 7 - Migrate tag components
- Task B4: Phase 8 - Clean up primitives types

### Group C (Validation) - Run Last
- Task C1: TypeScript compilation check
- Task C2: Build verification
- Task C3: Lint check for unused imports

---

## Validation Checklist

After all phases complete:

1. **TypeScript**: `npx tsc --noEmit` passes with no errors
2. **Build**: `npm run build` completes successfully
3. **Lint**: No unused import warnings
4. **Visual**: Spot-check key pages render correctly:
   - Dashboard
   - Queue page
   - Settings pages
   - Ceph/Storage pages

---

## Files Summary

### Primary Files to Modify

**Component definitions (Group A):**
- `/packages/web/src/components/ui/Text/RediaccText.types.ts`
- `/packages/web/src/components/ui/Text/RediaccText.styles.ts`
- `/packages/web/src/components/ui/Tag/RediaccTag.types.ts`
- `/packages/web/src/components/ui/Tag/RediaccTag.styles.ts`
- `/packages/web/src/components/ui/Button/RediaccButton.types.ts`
- `/packages/web/src/components/ui/Button/RediaccButton.styles.ts`
- `/packages/web/src/components/ui/Form/Input/RediaccInput.types.ts`
- `/packages/web/src/components/ui/Form/Input/RediaccInput.styles.ts`

**Primitives (Group B):**
- `/packages/web/src/styles/primitives.ts`

**Consumer files (Group B - many):**
- `/packages/web/src/pages/**/*.tsx`
- `/packages/web/src/pages/**/*.ts`
- `/packages/web/src/components/**/*.tsx`
- `/packages/web/src/components/**/*.ts`

---

## Expected Outcomes

| Metric | Before | After | Reduction |
|--------|--------|-------|-----------|
| TextVariant options | 10 | 4 | 60% |
| TagVariant + Preset options | 16 | 9 | 44% |
| ButtonVariant options | 2 | 1 | 50% |
| InputVariant options | 4 | 1 | 75% |
| primitives.ts exports | 107 | ~70 | 35% |
| Lines of code | ~1200 | ~800 | 33% |

---

## Risk Mitigation

1. **Run Group A first** - Component definitions must be updated before consumer migrations
2. **TypeScript is your friend** - Run `tsc --noEmit` after each phase to catch missed updates
3. **Grep before delete** - Always verify 0 usages before removing any export
4. **Preserve styling** - When migrating, ensure visual output matches original (same colors, sizes, weights)
5. **Handle styled extensions** - Components like `CardTitle` used as styled-component bases need their dependents updated first

---

## Notes for Sub-Agents

When executing migrations:

1. **Import patterns** - Replace:
   ```typescript
   // OLD
   import { CardTitle, HelperText } from '@/styles/primitives';

   // NEW
   import { RediaccText } from '@/components/ui';
   ```

2. **JSX patterns** - Replace:
   ```tsx
   // OLD
   <CardTitle>Title</CardTitle>

   // NEW
   <RediaccText variant="title">Title</RediaccText>
   ```

3. **Styled extensions** - Replace:
   ```typescript
   // OLD
   const CustomTitle = styled(CardTitle)`...`;

   // NEW
   const CustomTitle = styled(RediaccText).attrs({ variant: 'title' })`...`;
   ```

4. **Type imports** - Replace:
   ```typescript
   // OLD
   import type { TagVariant } from '@/styles/primitives';

   // NEW
   import type { TagVariant } from '@/components/ui/Tag';
   ```
