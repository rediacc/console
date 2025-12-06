# Phase 2: Component Consolidation Refactor

## Context

Phase 1 successfully migrated Button, Input, Tag, Text, and Select styled wrappers to Rediacc* equivalents. This phase addresses the remaining Ant Design components that are styled directly throughout the codebase.

## The Problem

Many files still bypass the unified component system by directly styling Ant Design components like Card, Alert, Space, Badge, etc. This creates:
- Inconsistent visual appearance
- Duplicate styling logic across 44+ files
- Theme changes not propagating uniformly
- Harder maintenance and larger bundle size

## The Goal

1. **Create new Rediacc* components** for high-frequency Ant Design components
2. **Migrate all styled wrappers** to use Rediacc* equivalents
3. **Migrate remaining quick-wins** (Checkbox, Radio, InputNumber already have Rediacc* versions)

## Philosophy

The Rediacc* components are the "approved ingredients." When you encounter a `styled(Card)`, ask: "What is this wrapper trying to achieve?" Usually the answer maps to one of:
- **Variant styling** → Use variant prop on Rediacc* component
- **Spacing/sizing** → Use size prop or extend with styled(Rediacc*)
- **Status colors** → Use status/variant prop
- **Unnecessary** → Remove the wrapper entirely

---

# PART A: New Rediacc* Components to Create

## 1. RediaccCard

**Location**: `src/components/ui/Card/`

**Props**:
```typescript
interface RediaccCardProps {
  variant?: 'default' | 'section' | 'selectable' | 'danger' | 'bordered';
  size?: 'sm' | 'md' | 'lg';
  selected?: boolean;           // For selectable variant
  hoverable?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  fullHeight?: boolean;
  children?: ReactNode;
  title?: ReactNode;
  extra?: ReactNode;
  onClick?: () => void;
  className?: string;
  style?: CSSProperties;
  'data-testid'?: string;
}
```

**Replaces** (~35 occurrences):
- `styled(Card)` - PageCard, FiltersCard, ContentCard, SelectableCard, SpacedCard
- TemplateCard, SettingsCard, DangerCard, WidgetCard, SummaryCard
- MetricCard, InfoCard, ServiceCard, ClusterCard, etc.

---

## 2. RediaccAlert

**Location**: `src/components/ui/Alert/`

**Props**:
```typescript
interface RediaccAlertProps {
  variant?: 'info' | 'success' | 'warning' | 'error';
  size?: 'sm' | 'md';
  showIcon?: boolean;
  closable?: boolean;
  onClose?: () => void;
  icon?: ReactNode;
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  banner?: boolean;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  'data-testid'?: string;
}
```

**Replaces** (~25 occurrences):
- `styled(Alert)` - WarningAlert, PushAlertCard, RoundedAlert, SpacedAlert
- InfoBanner, InlineInfoAlert, SectionAlert, TipsAlert, ExtraFieldsAlert
- ManualSetupAlert, DefaultsAlert, AlertWrapper, ModalAlert, etc.

---

## 3. RediaccStack (replaces Space)

**Location**: `src/components/ui/Stack/`

**Props**:
```typescript
interface RediaccStackProps {
  direction?: 'horizontal' | 'vertical';
  gap?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | number;
  align?: 'start' | 'center' | 'end' | 'stretch' | 'baseline';
  justify?: 'start' | 'center' | 'end' | 'between' | 'around' | 'evenly';
  wrap?: boolean;
  fullWidth?: boolean;
  inline?: boolean;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  as?: 'div' | 'span' | 'section' | 'article';
  'data-testid'?: string;
}
```

**Replaces** (~25 occurrences):
- `styled(Space)` - FiltersGrid, StatsBar, StatItem, HeaderStack, CardStack
- ContentStack, EmptyDescriptionStack, EmptyActions, FullWidthStack
- FeatureList, FeatureItem, ActionRow, OptionsStack, TitleStack, etc.

---

## 4. RediaccBadge

**Location**: `src/components/ui/Badge/`

**Props**:
```typescript
interface RediaccBadgeProps {
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info' | 'muted';
  type?: 'count' | 'dot' | 'status';
  count?: number;
  maxCount?: number;
  showZero?: boolean;
  dot?: boolean;
  size?: 'sm' | 'md';
  offset?: [number, number];
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  'data-testid'?: string;
}
```

**Replaces** (~12 occurrences):
- `styled(Badge)` - TabCount, QueueBadge, PrimaryBadge, PlanCountBadge
- QuantityBadge, MachineCountBadgeWrapper, StyledBadge, etc.

---

## 5. RediaccDivider

**Location**: `src/components/ui/Divider/`

**Props**:
```typescript
interface RediaccDividerProps {
  orientation?: 'horizontal' | 'vertical';
  variant?: 'solid' | 'dashed';
  spacing?: 'none' | 'sm' | 'md' | 'lg';
  children?: ReactNode;  // For text dividers
  className?: string;
  style?: CSSProperties;
}
```

**Replaces** (~8 occurrences):
- `styled(Divider)` - SectionDivider, DetailPanelDivider, MenuDivider

---

## 6. RediaccEmpty

**Location**: `src/components/ui/Empty/`

**Props**:
```typescript
interface RediaccEmptyProps {
  variant?: 'default' | 'simple' | 'compact';
  icon?: ReactNode;
  title?: string;
  description?: string;
  action?: ReactNode;
  imageStyle?: CSSProperties;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  'data-testid'?: string;
}
```

**Replaces** (~6 occurrences):
- `styled(Empty)` - PaddedEmpty, NoResultsEmpty, EmptyState

---

## 7. RediaccTitle (extends RediaccText)

**Location**: `src/components/ui/Text/` (extend existing)

**Props**:
```typescript
interface RediaccTitleProps {
  level?: 1 | 2 | 3 | 4 | 5;
  color?: 'primary' | 'secondary' | 'muted' | 'danger' | 'success';
  noMargin?: boolean;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
}
```

**Replaces** (~12 occurrences):
- `styled(Typography.Title)` - SectionTitle, NoMarginTitle
- `styled(Title)` - HeaderTitle, SuccessTitle, LoadingTitle, SecurityTitle
- DetailPanelTitle, DetailPanelSectionTitle, CardTitle, etc.

---

## 8. RediaccModal

**Location**: `src/components/ui/Modal/`

**Props**:
```typescript
interface RediaccModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  closable?: boolean;
  maskClosable?: boolean;
  footer?: ReactNode | null;
  destroyOnClose?: boolean;
  centered?: boolean;
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  'data-testid'?: string;
}
```

**Replaces** (~3 occurrences):
- `styled(Modal)` - BaseModal, WizardModal, FadeInModal

---

# PART B: Quick-Win Migrations (Existing Rediacc*)

These components already have Rediacc* equivalents but some files still use direct Ant Design:

## 1. Checkbox → RediaccCheckbox

**Files**:
- `src/components/common/UnifiedResourceModal/styles.ts` - AutoSetupCheckbox

**Pattern**:
```typescript
// BEFORE
export const AutoSetupCheckbox = styled(Checkbox)`...`;
// AFTER
export const AutoSetupCheckbox = styled(RediaccCheckbox)`...`;
```

## 2. Radio → RediaccRadio

**Files**:
- `src/components/common/VaultEditor/components/FieldGenerator/styles.ts` - OptionRadio

**Pattern**:
```typescript
// BEFORE
export const OptionRadio = styled(Radio)`...`;
// AFTER
export const OptionRadio = styled(RediaccRadio)`...`;
```

## 3. InputNumber → RediaccInputNumber

**Files**:
- `src/components/common/FunctionSelectionModal/styles.ts` - SizeValueInput
- `src/components/common/UnifiedResourceModal/components/ResourceFormWithVault/styles.ts` - SizeNumberInput

**Pattern**:
```typescript
// BEFORE
export const SizeValueInput = styled(InputNumber)`...`;
// AFTER
export const SizeValueInput = styled(RediaccInputNumber)`...`;
```

---

# PART C: Component Mapping Reference

## Card Variants
| Old Wrapper | New Approach |
|-------------|--------------|
| `styled(Card)` with no custom styles | Use `RediaccCard` directly |
| `styled(Card)` with danger border | `<RediaccCard variant="danger">` |
| `styled(Card)` with selection state | `<RediaccCard variant="selectable" selected={...}>` |
| `styled(Card)` with custom padding | `<RediaccCard padding="lg">` or extend |
| `styled(Card).attrs({ size: 'small' })` | `<RediaccCard size="sm">` |

## Alert Variants
| Old Wrapper | New Approach |
|-------------|--------------|
| `styled(Alert)` info type | `<RediaccAlert variant="info">` |
| `styled(Alert)` warning with icon | `<RediaccAlert variant="warning" showIcon>` |
| `styled(Alert)` rounded border | `<RediaccAlert>` (built-in styling) |
| Banner-style alert | `<RediaccAlert banner>` |

## Space/Stack Mapping
| Old Pattern | New Approach |
|-------------|--------------|
| `styled(Space).attrs({ orientation: 'vertical' })` | `<RediaccStack direction="vertical">` |
| `styled(Space).attrs({ size: 'large' })` | `<RediaccStack gap="lg">` |
| `styled(Space)` with wrap | `<RediaccStack wrap>` |

## Badge Variants
| Old Wrapper | New Approach |
|-------------|--------------|
| Badge with color based on status | `<RediaccBadge variant="success">` |
| Badge with count | `<RediaccBadge type="count" count={5}>` |
| Dot badge | `<RediaccBadge type="dot">` |

---

# PART D: Migration Patterns

## Pattern A: Wrapper adds only spacing/layout
```typescript
// BEFORE
export const SummaryCard = styled(Card)`
  margin-bottom: 16px;
`;
// AFTER
export const SummaryCard = styled(RediaccCard)`
  margin-bottom: 16px;
`;
```

## Pattern B: Wrapper customizes appearance (use props)
```typescript
// BEFORE
export const DangerCard = styled(Card)`
  border-color: ${({ theme }) => theme.colors.error};
`;
// AFTER
export const DangerCard = styled(RediaccCard).attrs({ variant: 'danger' })``;
```

## Pattern C: Wrapper is unnecessary (DELETE)
```typescript
// BEFORE
export const BasicCard = styled(Card)`
  border-radius: 8px;
`;
// AFTER - Delete wrapper, use RediaccCard directly at usage sites
```

## Pattern D: Complex conditional styling
```typescript
// BEFORE
export const ServiceCard = styled(Card)<{ $state: 'active' | 'failed' }>`
  border-color: ${({ $state, theme }) =>
    $state === 'active' ? theme.colors.success : theme.colors.error};
`;
// AFTER - Keep styled wrapper but base on Rediacc*
export const ServiceCard = styled(RediaccCard)<{ $state: 'active' | 'failed' }>`
  && {
    border-color: ${({ $state, theme }) =>
      $state === 'active' ? theme.colors.success : theme.colors.error};
  }
`;
```

## Pattern E: Aliased imports (Ant* prefix)
```typescript
// BEFORE
import { Text as AntText } from 'antd';
export const MachineName = styled(AntText)`...`;
// AFTER
import { RediaccText } from '@/components/ui/Text';
export const MachineName = styled(RediaccText)`...`;
```

---

# PART E: Execution Strategy

## Phase 2A: Create New Rediacc* Components (Sequential)

One agent creates all new components in order:

1. **RediaccCard** - Most used, foundation for others
2. **RediaccAlert** - Second most used
3. **RediaccStack** - Replaces Space pattern
4. **RediaccBadge** - Status indicators
5. **RediaccDivider** - Simple component
6. **RediaccEmpty** - Empty states
7. **RediaccTitle** - Extend RediaccText
8. **RediaccModal** - Dialog wrapper

Each component should follow the established pattern:
- `Component.tsx` - Main component
- `Component.styles.ts` - Styled wrapper
- `Component.types.ts` - TypeScript interfaces
- `index.ts` - Barrel export

## Phase 2B: Migration Agents (Parallel)

After components are created, run migration agents in parallel:

### Agent 1: Primitives & Core Styles
**Path**: `src/styles/primitives.ts`
**Changes**:
- PageCard, FiltersCard, ContentCard, SelectableCard, SpacedCard → RediaccCard
- AlertCard → RediaccAlert
- FiltersGrid, StatsBar, StatItem, FullWidthSpace → RediaccStack
- TabCount, PaddedEmpty → RediaccBadge, RediaccEmpty
- BaseModal → RediaccModal
- NoMarginTitle → RediaccTitle
- ModeSegmented, CenteredRow (keep or wrap)

**Estimated**: ~20 wrappers

### Agent 2: Common Components - Part 1
**Path**: `src/components/common/`
**Files**:
- `VaultEditor/styles.ts` - InfoBanner, EditorForm, FullWidthStack, alerts
- `VaultEditor/components/NestedObjectEditor/styles.ts` - Cards, CollapseWrapper
- `VaultEditor/components/FieldGenerator/styles.ts` - ActionRow, OptionsStack, OptionRadio
- `FunctionSelectionModal/styles.ts` - Alerts, SizeValueInput
- `QueueItemTraceModal/styles.ts` - SpacedAlert

**Estimated**: ~20 wrappers

### Agent 3: Common Components - Part 2
**Path**: `src/components/common/`
**Files**:
- `TemplateSelector/styles.ts` - HeaderStack, NoResultsEmpty, TemplateCard, CardStack
- `TemplatePreviewModal/styles.ts` - StyledTabs, FeatureList, FeatureItem, alerts
- `ResourceListView/styles.ts` - ContainerCard, EmptyDescriptionStack, EmptyActions
- `UnifiedResourceModal/styles.ts` - TemplateCollapse, AutoSetupCheckbox
- `UnifiedResourceModal/components/ResourceFormWithVault/styles.ts` - Form, Divider, Alert, InputNumber
- `InsecureConnectionWarning/styles.ts`, `SandboxWarning/styles.ts` - Alerts

**Estimated**: ~20 wrappers

### Agent 4: Resource Components
**Path**: `src/components/resources/`
**Files**:
- `internal/detailPanelPrimitives.ts` - Card, Divider, Title
- `internal/MachineTable/styles.ts` - EmptyState, GroupCardContainer, StyledBadge
- `internal/MachineVaultStatusPanel/styles.ts` - QueueBadge, EmptyState, Cards, List, Title
- `internal/RepoDetailPanel/styles.ts` - EmptyState, AlertWrapper, ServiceCard
- `internal/ContainerDetailPanel/styles.ts` - MetricCard
- `internal/LocalCommandModal/styles.ts` - SettingsForm, TabsWrapper
- `internal/CephSection/styles.ts` - SectionDivider, SectionCard, AlertWrapper
- `internal/PipInstallationModal/styles.ts` - ContentSpace
- `AvailableMachinesSelector/styles.ts` - AntText wrappers

**Estimated**: ~25 wrappers

### Agent 5: Layout & Dashboard
**Path**: `src/components/layout/`, `src/pages/dashboard/`
**Files**:
- `layout/MainLayout/styles.ts` - UserAvatar
- `layout/MainLayout/UserMenu/styles.ts` - PlanBadge, MenuDivider, ModeSegmented
- `pages/dashboard/styles.ts` - DashboardCard, ResourceProgress, StatList, badges, Timeline, List, Title
- `pages/dashboard/components/CephDashboardWidget/styles.ts` - Cards, Statistic, List

**Estimated**: ~20 wrappers

### Agent 6: Ceph Pages
**Path**: `src/pages/ceph/`
**Files**:
- `styles.ts` - HeaderTitle
- `components/ClusterTable/styles.ts` - MachineCountBadgeWrapper
- `components/CloneTable/styles.ts` - MachineCountBadgeWrapper, MachineListStack, MachineListActions
- `components/PoolTable/styles.ts` - ClusterCard
- `components/FilterableMachineTable/styles.ts` - QueueBadge
- `components/MachineAvailabilitySummary/styles.ts` - Cards, Statistic

**Estimated**: ~12 wrappers

### Agent 7: Other Pages
**Path**: Various `src/pages/`
**Files**:
- `pages/login/styles.ts` - existing components
- `pages/login/components/RegistrationModal/styles.ts` - VerticalStack, StepsWrapper, Title
- `pages/login/components/EndpointSelector/styles.ts` - FormActions, AntText
- `pages/login/components/VersionSelector/styles.ts` - AntText
- `pages/audit/AuditPage/styles.ts` - FilterField
- `pages/architecture/styles.ts` - HeaderStack
- `pages/settings/profile/components/TwoFactorSettings/styles.ts` - alerts, Title
- `pages/organization/access/components/UserSessionsTab/styles.ts` - StyledCard, StatMetric
- `pages/organization/users/components/ResourceForm/styles.ts` - StyledForm, ActionButtons
- `pages/resources/styles.ts` - FullHeightCard, BreadcrumbWrapper, Title
- `pages/resources/components/RemoteFileBrowserModal/styles.ts` - ContentSpace, SourceContainer
- `pages/resources/components/RepoContainerTable/styles.ts` - AntTable, Title
- `pages/storage/components/RcloneImportWizard/styles.ts` - WizardModal, alerts, Title
- `pages/machines/components/ConnectivityTestModal/styles.ts` - TitleStack, ProgressBar, InfoAlert
- `pages/system/styles.ts` - SettingsCard, DangerCard, PrimaryBadge, ModalAlert

**Estimated**: ~25 wrappers

---

# PART F: Import Updates

Standard import changes:
```typescript
// Remove from 'antd' imports:
import { Card, Alert, Space, Badge, Divider, Empty, Modal, Form, List, Tabs, Collapse, Progress, Steps, Timeline, Breadcrumb, Statistic, Avatar, Segmented } from 'antd';
import { Typography } from 'antd';
const { Title } = Typography;

// Add:
import { RediaccCard } from '@/components/ui/Card';
import { RediaccAlert } from '@/components/ui/Alert';
import { RediaccStack } from '@/components/ui/Stack';
import { RediaccBadge } from '@/components/ui/Badge';
import { RediaccDivider } from '@/components/ui/Divider';
import { RediaccEmpty } from '@/components/ui/Empty';
import { RediaccModal } from '@/components/ui/Modal';
import { RediaccTitle } from '@/components/ui/Text';

// Already exist - use for quick wins:
import { RediaccCheckbox } from '@/components/ui/Form/Checkbox';
import { RediaccRadio } from '@/components/ui/Form/Radio';
import { RediaccInputNumber } from '@/components/ui/Form/Input';
```

---

# PART G: Verification Phase

After all agents complete:

1. **Grep for remaining direct usage**:
```bash
grep -r "styled(Card)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Alert)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Space)" packages/web/src/ --include="*.ts"
grep -r "styled(Badge)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Divider)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Empty)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Modal)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Checkbox)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Radio)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(InputNumber)" packages/web/src/ --include="*.ts" | grep -v "Rediacc"
grep -r "styled(Typography" packages/web/src/ --include="*.ts"
grep -r "styled(Title)" packages/web/src/ --include="*.ts"
grep -r "styled(Ant" packages/web/src/ --include="*.ts" | grep -v "components/ui"
```

2. **TypeScript check**: `npx tsc --noEmit`

3. **Build check**: `npm run build`

4. **Visual verification**: Spot-check key pages

---

# PART H: Success Criteria

- [ ] All 8 new Rediacc* components created and exported
- [ ] Zero `styled(Card|Alert|Space|Badge|Divider|Empty|Modal)` wrappers around raw antd
- [ ] Zero `styled(Checkbox|Radio|InputNumber)` around raw antd
- [ ] Zero `styled(Typography.Title)` or `styled(Title)` around raw antd
- [ ] All `Ant*` prefixed imports removed (except in Rediacc* foundation files)
- [ ] TypeScript compilation passes
- [ ] Build succeeds
- [ ] No regressions in visual appearance

---

# PART I: Component Count Summary

| Component | Occurrences | New Rediacc* | Notes |
|-----------|-------------|--------------|-------|
| Card | ~35 | RediaccCard | High priority |
| Alert | ~25 | RediaccAlert | High priority |
| Space | ~25 | RediaccStack | High priority |
| Badge | ~12 | RediaccBadge | Medium priority |
| Typography.Title/Title | ~12 | RediaccTitle | Extend RediaccText |
| Divider | ~8 | RediaccDivider | Simple |
| Empty | ~6 | RediaccEmpty | Simple |
| Form | ~6 | Keep antd | Complex, not worth wrapping |
| List | ~5 | Keep antd | Complex, style individually |
| Tabs | ~4 | Keep antd | Complex, style individually |
| Statistic | ~4 | Keep antd | Specialized |
| Modal | ~3 | RediaccModal | Dialog wrapper |
| Collapse | ~3 | Keep antd | Specialized |
| Progress | ~3 | Keep antd | Specialized |
| Row | ~3 | Keep antd | Layout utility |
| Avatar | ~2 | Keep antd | Specialized |
| Segmented | ~2 | Keep antd | Specialized |
| Steps | ~1 | Keep antd | Specialized |
| Timeline | ~1 | Keep antd | Specialized |
| Breadcrumb | ~1 | Keep antd | Specialized |
| **Checkbox** | 1 | RediaccCheckbox (exists) | Quick win |
| **Radio** | 1 | RediaccRadio (exists) | Quick win |
| **InputNumber** | 2 | RediaccInputNumber (exists) | Quick win |

**Total new components**: 8
**Total wrappers to migrate**: ~140
**Quick wins with existing components**: 4

---

# Notes

- Form, List, Tabs, Collapse, Progress, Statistic, Avatar, Segmented, Steps, Timeline, Breadcrumb, Row are complex/specialized and should be styled individually rather than wrapped
- Focus on the high-impact components (Card, Alert, Stack, Badge, Title) first
- RediaccTitle could be a variant of RediaccText or a separate component
- Maintain backwards compatibility by keeping export names where possible
