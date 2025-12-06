# Select Component

A unified, centralized Select component that replaces all legacy select variants across the codebase. Based on Ant Design Select with consistent theming and size variants.

## Features

- Three size variants: `sm`, `md` (default), `lg`
- Full width and minimum width options
- Consistent theming with Input component
- Search and filtering capabilities
- Multiple selection mode
- Loading and disabled states
- Error/warning states
- Clear button support
- Virtual scrolling for large lists

## Basic Usage

```tsx
import { Select } from '@/components/ui/Form';

// Basic select
<Select
  value={value}
  onChange={setValue}
  options={[
    { value: '1', label: 'Option 1' },
    { value: '2', label: 'Option 2' },
  ]}
  placeholder="Select an option"
/>
```

## Size Variants

```tsx
// Small (28px height) - for compact layouts
<Select size="sm" options={options} />

// Medium (32px height) - default
<Select size="md" options={options} />

// Large (40px height) - for prominent selections
<Select size="lg" options={options} />
```

## Width Options

```tsx
// Full width - stretches to container
<Select fullWidth options={options} />

// Minimum width - ensures minimum size
<Select minWidth={200} options={options} />

// Combination
<Select fullWidth minWidth={150} options={options} />
```

## Advanced Features

### Searchable Select

```tsx
<Select
  showSearch
  filterOption
  options={largeOptionsList}
  placeholder="Search..."
/>
```

### Multiple Selection

```tsx
<Select
  mode="multiple"
  value={selectedValues}
  onChange={setSelectedValues}
  options={options}
  maxTagCount={3}
/>
```

### Loading State

```tsx
<Select
  loading
  placeholder="Loading options..."
  options={[]}
/>
```

### Error State

```tsx
<Select
  status="error"
  value={value}
  onChange={setValue}
  options={options}
/>
```

### Allow Clear

```tsx
<Select
  allowClear
  value={value}
  onChange={setValue}
  options={options}
/>
```

## Migration Guide

### From `FullWidthSelect` (primitives.ts)

**Before:**
```tsx
import { FullWidthSelect } from '@/styles/primitives';

<FullWidthSelect>
  <Select.Option value="1">Option 1</Select.Option>
</FullWidthSelect>
```

**After:**
```tsx
import { Select } from '@/components/ui/Form';

<Select
  fullWidth
  options={[
    { value: '1', label: 'Option 1' }
  ]}
/>
```

### From `FilterSelect` (primitives.ts)

**Before:**
```tsx
import { FilterSelect } from '@/styles/primitives';

<FilterSelect $minWidth={150}>
  <Select.Option value="all">All</Select.Option>
</FilterSelect>
```

**After:**
```tsx
import { Select } from '@/components/ui/Form';

<Select
  minWidth={150}
  options={[
    { value: 'all', label: 'All' }
  ]}
/>
```

### From `ModalSelect` (common/styled)

**Before:**
```tsx
import { ModalSelect } from '@/components/common/styled';

<ModalSelect $compact>
  <Select.Option value="1">Option 1</Select.Option>
</ModalSelect>
```

**After:**
```tsx
import { Select } from '@/components/ui/Form';

<Select
  size="sm"
  fullWidth
  options={[
    { value: '1', label: 'Option 1' }
  ]}
/>
```

### From Custom Styled Selects

**TeamSelect, LanguageSelect, etc.:**

```tsx
// Before
const TeamSelect = styled(Select)`
  && {
    width: 100%;
  }
`;

// After
<Select fullWidth options={teamOptions} />
```

**AssignmentSelect, PageSizeSelect:**

```tsx
// Before
const AssignmentSelect = styled(Select)`
  && {
    width: min(240px, 100%);
  }
`;

// After
<Select minWidth={240} options={assignmentOptions} />
```

## Props Reference

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `size` | `'sm' \| 'md' \| 'lg'` | `'md'` | Select size variant |
| `fullWidth` | `boolean` | `false` | Stretch to container width |
| `minWidth` | `number` | `undefined` | Minimum width in pixels |
| `value` | `T` | `undefined` | Selected value |
| `onChange` | `(value: T) => void` | `undefined` | Change handler |
| `options` | `SelectOption[]` | `undefined` | Options array |
| `placeholder` | `string` | `undefined` | Placeholder text |
| `disabled` | `boolean` | `false` | Disabled state |
| `loading` | `boolean` | `false` | Loading state |
| `allowClear` | `boolean` | `false` | Show clear button |
| `showSearch` | `boolean` | `false` | Enable search |
| `filterOption` | `boolean \| function` | `undefined` | Filter function |
| `mode` | `'multiple' \| 'tags'` | `undefined` | Selection mode |
| `status` | `'error' \| 'warning'` | `undefined` | Validation status |
| `data-testid` | `string` | `undefined` | Test identifier |
| `className` | `string` | `undefined` | Additional class |

## Custom Options with Children

For complex option rendering, you can use children instead of the options array:

```tsx
import { Select, Option } from '@/components/ui/Form';

<Select value={value} onChange={setValue}>
  <Option value="pending">
    <StatusIcon type="pending" /> Pending
  </Option>
  <Option value="completed">
    <StatusIcon type="completed" /> Completed
  </Option>
</Select>
```

## Design Principles

1. **Consistent Sizing**: Matches Input component sizes (28px, 32px, 40px)
2. **Responsive**: Supports fullWidth and minWidth for flexible layouts
3. **Accessible**: Proper ARIA labels and keyboard navigation
4. **Themed**: Uses design tokens for colors, spacing, and borders
5. **Performant**: Virtual scrolling for large option lists

## Legacy Components to Replace

The following components should be migrated to use the unified Select:

- `FullWidthSelect` in `/src/styles/primitives.ts`
- `FilterSelect` in `/src/styles/primitives.ts`
- `ModalSelect` in `/src/components/common/styled/index.ts`
- `LanguageSelect` in `/src/components/common/LanguageSelector/styles.ts`
- `TeamSelect` in `/src/components/common/TeamSelector/styles.ts`
- `SizeUnitSelect` in `/src/components/common/FunctionSelectionModal/styles.ts`
- `AssignmentSelect` in `/src/features/distributed-storage/.../styles.ts`
- `PageSizeSelect` in `/src/features/distributed-storage/.../styles.ts`
- Various `StyledSelect` instances across the codebase

## Examples

See `Select.example.tsx` for complete working examples of all features and migration patterns.
