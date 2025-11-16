# Console Components - Refactoring TODO

> **📚 Reference Documents:**
> - **[REFACTORING.md](./REFACTORING.md)** - Complete guide on how to refactor components
> - **[STYLE.md](./STYLE.md)** - Styling conventions with styled-components
>
> **How to Use This Document:**
> 1. Pick a component from the list below
> 2. Follow the step-by-step process in [REFACTORING.md](./REFACTORING.md)
> 3. Apply styling conventions from [STYLE.md](./STYLE.md)
> 4. Mark as completed when done

---

## Recently Completed ✅

### ✅ MainLayout (Nov 2025 - PR #163)
- **Before**: 886 lines in single file
- **After**: Split into 9 modular files
- **Files created**: MainLayout/, Sidebar/, UserMenu/, with types, helpers, styles

### ✅ AuthLayout (Nov 2025 - PR #163)
- **Before**: 51 lines flat file
- **After**: Modular folder structure with index.tsx and styles.ts

### ✅ TeamsPage Data (Nov 2025 - PR #163)
- **Before**: 400+ lines with embedded table columns
- **After**: Extracted table columns to data.tsx (173 lines)

---

## Remaining Components

> **Identification criteria for components needing refactoring:**
> - ❌ Not using folder structure with `index.tsx`
> - ❌ Missing co-located `styles.ts` file
> - ❌ Contains hard-coded hex colors
> - ❌ Contains inline `style={{}}` attributes
> - ❌ Not using styled-components
> - ❌ File size > 300 lines

## Priority 1: High Violation Count (Critical)

### 1. MachineTable (1077 lines)
**Location:** `src/components/resources/MachineTable.tsx`

**Violations:**
- ❌ **16 hard-coded hex colors**
- ❌ **21 inline styles**
- ❌ No styled-components usage
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure: `MachineTable/index.tsx` and `MachineTable/styles.ts`
2. Move all inline styles to styled-components
3. Replace hex colors with theme tokens (CSS variables)
4. Extract table column configurations
5. Use styled Table wrapper instead of inline styles

---

### 2. MachineVaultStatusPanel (636 lines)
**Location:** `src/components/resources/MachineVaultStatusPanel.tsx`

**Violations:**
- ❌ **15 hard-coded hex colors**
- ❌ **60 inline styles** (highest count!)
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure: `MachineVaultStatusPanel/index.tsx` and `MachineVaultStatusPanel/styles.ts`
2. Replace all hard-coded colors with theme tokens
3. Create styled primitives for repeating layout patterns
4. Extract vault status components

**Example violations:**
```tsx
// ❌ Current
<CloudServerOutlined style={{ fontSize: 24, color: '#556b2f' }} />
<Tag color="#8FBC8F" icon={<AppstoreOutlined />}>
<Badge count={machine.queueCount} style={{ backgroundColor: '#52c41a' }} />

// ✅ Should be
<StyledCloudServerIcon />
<StyledTeamTag icon={<AppstoreOutlined />}>
<StyledQueueBadge count={machine.queueCount} />
```

---

### 3. RcloneImportWizard (569 lines)
**Location:** `src/components/resources/RcloneImportWizard.tsx`

**Violations:**
- ❌ **9 inline styles**
- ❌ No styled-components usage
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure
2. Extract wizard step components
3. Create styled primitives for wizard layout

---

### 4. TwoFactorSettings (531 lines)
**Location:** `src/components/settings/TwoFactorSettings.tsx`

**Violations:**
- ❌ **32 inline styles**
- ❌ No styled-components usage
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure
2. Extract QR code display component
3. Extract recovery codes component
4. Move all inline styles to styled-components

---

### 5. RepositoryDetailPanel (525 lines)
**Location:** `src/components/resources/RepositoryDetailPanel.tsx`

**Violations:**
- ❌ **9 hard-coded hex colors**
- ❌ **42 inline styles**
- ✅ Already imports from styles (partial refactor)

**Required Actions:**
1. Complete migration to folder structure
2. Replace remaining hex colors with theme tokens
3. Remove remaining inline styles
4. Consolidate styled-components in `styles.ts`

---

## Priority 2: Medium Violation Count

### 6. ResourceFormWithVault (472 lines)
**Location:** `src/components/forms/ResourceFormWithVault.tsx`

**Violations:**
- ❌ **2 hex colors**
- ❌ **12 inline styles**
- ❌ No `styles.ts` file

---

### 7. AuditPage (470 lines)
**Location:** `src/pages/audit/AuditPage.tsx`

**Violations:**
- ❌ **3 hex colors**
- ❌ **13 inline styles**
- ✅ Already imports from styles (partial refactor)

**Required Actions:**
- Complete styled-components migration
- Remove remaining hard-coded colors

---

### 8. CloneList (445 lines)
**Location:** `src/pages/distributedStorage/components/CloneList.tsx`

**Violations:**
- ❌ **3 hex colors**
- ❌ **9 inline styles**
- ❌ No `styles.ts` file

---

### 9. CloneMachineManager (438 lines)
**Location:** `src/pages/distributedStorage/components/CloneMachineManager.tsx`

**Violations:**
- ❌ **10 inline styles**
- ❌ No `styles.ts` file

---

### 10. ClusterTable (408 lines)
**Location:** `src/pages/distributedStorage/components/ClusterTable.tsx`

**Violations:**
- ❌ **11 inline styles**
- ❌ No `styles.ts` file

---

### 11. UserSessionsTab (372 lines)
**Location:** `src/components/system/UserSessionsTab.tsx`

**Violations:**
- ❌ **14 inline styles**
- ❌ No `styles.ts` file

---

### 12. SnapshotList (341 lines)
**Location:** `src/pages/distributedStorage/components/SnapshotList.tsx`

**Violations:**
- ❌ **6 inline styles**
- ❌ No `styles.ts` file

---

### 13. PoolTable (293 lines)
**Location:** `src/pages/distributedStorage/components/PoolTable.tsx`

**Violations:**
- ❌ **7 inline styles**
- ❌ No `styles.ts` file

---

### 14. DistributedStorageDashboardWidget (270 lines)
**Location:** `src/components/dashboard/DistributedStorageDashboardWidget.tsx`

**Violations:**
- ❌ **1 hex color**
- ❌ **12 inline styles**
- ❌ No `styles.ts` file

---

### 15. VirtualFilterableMachineTable (231 lines)
**Location:** `src/features/distributed-storage/components/performance/VirtualFilterableMachineTable.tsx`

**Violations:**
- ❌ **12 inline styles**
- ❌ No `styles.ts` file

---

### 16. ResourceForm (174 lines)
**Location:** `src/components/forms/ResourceForm.tsx`

**Violations:**
- ❌ **3 inline styles**
- ❌ No `styles.ts` file

---

### 17. MachineAvailabilitySummary (166 lines)
**Location:** `src/pages/distributedStorage/components/MachineAvailabilitySummary.tsx`

**Violations:**
- ❌ **5 hex colors**
- ❌ **13 inline styles**
- ❌ No `styles.ts` file

---

## Refactoring Process

> **For complete refactoring guidelines, see [REFACTORING.md](./REFACTORING.md)**

### Quick Reference

### Folder Structure Pattern
```
ComponentName/
├── index.tsx          # Main component file
├── styles.ts          # Styled-components
└── types.ts           # (optional) Type definitions
```

### styles.ts Template
```typescript
import styled from 'styled-components'
import { ComponentName } from 'antd'

export const StyledWrapper = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgPrimary};
`

export const StyledAntComponent = styled(ComponentName)`
  && {
    // Ant Design overrides with theme tokens
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`
```

### Color Replacement Guide
```typescript
// ❌ Hard-coded
color: '#556b2f'
backgroundColor: '#52c41a'
borderColor: '#8FBC8F'

// ✅ Theme tokens
color: var(--color-primary)
backgroundColor: var(--color-success)
borderColor: var(--color-border-primary)
```

### Inline Style Replacement
```tsx
// ❌ Before
<div style={{ display: 'flex', gap: '16px', padding: '12px' }}>

// ✅ After (styles.ts)
export const Container = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
`

// Usage
<Container>
```

---

## Summary Statistics

- **Completed:** 3 components (PR #163)
- **Remaining:** 17 components
- **Total lines remaining:** ~7,900 lines
- **Total hex colors:** 72+
- **Total inline styles:** 336+

### By Category
- **Components:** 10 files
- **Pages:** 6 files
- **Features:** 1 file

### By Priority
- **Priority 1 (Critical):** 5 files (2,700+ lines)
- **Priority 2 (Medium):** 12 files (4,200+ lines)

---

## Recommended Approach

1. **Start with Priority 1** - Highest impact components first
2. **Follow [REFACTORING.md](./REFACTORING.md)** - Step-by-step refactoring process
3. **One component at a time** - Ensure quality over speed
4. **Test after each refactor** - Verify in both light and dark themes
5. **Create PR per component** - Makes reviews easier
6. **Apply [STYLE.md](./STYLE.md) conventions** - Maintain styling consistency
7. **Update this file** - Mark completed items in "Recently Completed" section

---

## Success Criteria per Component

- ✅ Folder structure created (`ComponentName/index.tsx`, `styles.ts`)
- ✅ All styled-components imported from `./styles`
- ✅ Zero hard-coded hex colors (except in fallbacks with `||`)
- ✅ Zero inline `style={{}}` attributes
- ✅ All colors use theme tokens or CSS variables
- ✅ Build passes without TypeScript errors
- ✅ Component renders correctly in both light and dark themes
