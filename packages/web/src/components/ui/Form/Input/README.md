# Unified Input Component System

A consolidated, variant-based input component system that replaces all scattered input components across the codebase.

## Architecture

Following the same pattern as the Button component:
- **Input.types.ts** - TypeScript type definitions
- **Input.styles.ts** - Styled components with variant logic
- **Input.tsx** - React component implementations
- **index.ts** - Barrel exports

## Components

### 1. Input
Main text input component with multiple variants.

```tsx
import { Input } from '@/components/ui';

// Default input
<Input placeholder="Enter text" />

// Full-width input
<Input fullWidth placeholder="Enter email" />

// Code/secret variant (monospace font)
<Input variant="code" placeholder="Enter code" />

// Centered input
<Input centered placeholder="123456" />
```

**Props:**
- `variant?: 'default' | 'search' | 'code' | 'secret'`
- `fullWidth?: boolean`
- `centered?: boolean`
- All standard input props (placeholder, value, onChange, etc.)

### 2. PasswordInput
Password input with visibility toggle.

```tsx
import { PasswordInput } from '@/components/ui';

<PasswordInput fullWidth placeholder="Enter password" />
```

### 3. TextArea
Multi-line text input with auto-resize support.

```tsx
import { TextArea } from '@/components/ui';

// Basic textarea
<TextArea rows={4} placeholder="Enter description" />

// Auto-resize
<TextArea autoSize={{ minRows: 2, maxRows: 6 }} />

// With character count
<TextArea fullWidth showCount maxLength={500} />
```

### 4. InputNumber
Numeric input with increment/decrement controls.

```tsx
import { InputNumber } from '@/components/ui';

<InputNumber min={0} max={100} step={5} />
<InputNumber fullWidth precision={2} placeholder="Amount" />
```

### 5. SearchInput
Search input with integrated search button.

```tsx
import { SearchInput } from '@/components/ui';

<SearchInput placeholder="Search..." onSearch={handleSearch} />
<SearchInput fullWidth loading={isSearching} enterButton="Search" />
```

## Unified Height

All form inputs use a consistent 44px height (`FORM_CONTROL_HEIGHT`) for visual alignment across the application. This ensures inputs, buttons, and selects all align perfectly in forms and toolbars.

## Migration Guide

### From Legacy Primitives

#### FullWidthInput → Input
```tsx
// Before
import { FullWidthInput } from '@/styles/primitives';
<FullWidthInput placeholder="Email" />

// After
import { Input } from '@/components/ui';
<Input fullWidth placeholder="Email" />
```

#### LargeInput → Input
```tsx
// Before
import { LargeInput } from '@/styles/primitives';
<LargeInput placeholder="Search" />

// After
import { Input } from '@/components/ui';
<Input placeholder="Search" />
```

#### SearchInput → SearchInput
```tsx
// Before
import { SearchInput } from '@/styles/primitives';
<SearchInput placeholder="Search..." />

// After
import { SearchInput } from '@/components/ui';
<SearchInput placeholder="Search..." />
```

#### FilterInput → Input
```tsx
// Before
import { FilterInput } from '@/styles/primitives';
<FilterInput placeholder="Filter..." />

// After
import { Input } from '@/components/ui';
<Input placeholder="Filter..." style={{ minWidth: 200 }} />
```

#### CenteredInput / CenteredCodeInput → Input
```tsx
// Before
import { CenteredCodeInput } from './styles';
<CenteredCodeInput placeholder="123456" />

// After
import { Input } from '@/components/ui';
<Input centered variant="code" placeholder="123456" />
```

#### SecretInput → Input
```tsx
// Before
import { SecretInput } from './styles';
<SecretInput value={secret} />

// After
import { Input } from '@/components/ui';
<Input variant="secret" value={secret} />
```

#### FullWidthPasswordInput → PasswordInput
```tsx
// Before
import { FullWidthPasswordInput } from '@/styles/primitives';
<FullWidthPasswordInput placeholder="Password" />

// After
import { PasswordInput } from '@/components/ui';
<PasswordInput fullWidth placeholder="Password" />
```

#### FullWidthTextArea → TextArea
```tsx
// Before
import { FullWidthTextArea } from '@/styles/primitives';
<FullWidthTextArea rows={4} />

// After
import { TextArea } from '@/components/ui';
<TextArea fullWidth rows={4} />
```

#### FullWidthInputNumber → InputNumber
```tsx
// Before
import { FullWidthInputNumber } from '@/styles/primitives';
<FullWidthInputNumber min={0} max={100} />

// After
import { InputNumber } from '@/components/ui';
<InputNumber fullWidth min={0} max={100} />
```

## Design Tokens

The component uses tokens from `@/utils/styleConstants`:

```typescript
DIMENSIONS: {
  FORM_CONTROL_HEIGHT: 44,  // Unified height for all form controls
}

BORDER_RADIUS: {
  MD: 6,
  LG: 8,
}

SPACING: {
  SM: 8,
}
```

## Theming

All inputs respect the theme colors:
- `colors.primary` - Focus border and shadow
- `colors.error` - Error state
- `colors.textPrimary` - Input text
- `colors.bgPrimary` / `colors.bgSecondary` - Background
- `colors.borderSecondary` - Default border

## Common Patterns

### Form Input with Prefix Icon
```tsx
import { Input } from '@/components/ui';
import { MailOutlined } from '@ant-design/icons';

<Input
  fullWidth
  prefix={<MailOutlined />}
  placeholder="Email address"
/>
```

### Code Input for 2FA
```tsx
import { Input } from '@/components/ui';

<Input
  variant="code"
  centered
  maxLength={6}
  placeholder="000000"
  onChange={handleCodeChange}
/>
```

### Filter Input
```tsx
import { Input } from '@/components/ui';
import { SearchOutlined } from '@ant-design/icons';

<Input
  prefix={<SearchOutlined />}
  placeholder="Filter items..."
  allowClear
  onChange={handleFilterChange}
/>
```

## Testing

All components forward refs correctly and support standard input testing patterns:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Input } from '@/components/ui';

test('handles user input', async () => {
  const handleChange = jest.fn();
  render(<Input data-testid="test-input" onChange={handleChange} />);

  const input = screen.getByTestId('test-input');
  await userEvent.type(input, 'hello');

  expect(handleChange).toHaveBeenCalled();
});
```

## Components Consolidated

This unified system replaces **18+ scattered input components**:

### From primitives.ts:
- FullWidthInput
- FullWidthPasswordInput
- FullWidthTextArea
- FullWidthInputNumber
- LargeInput
- LargePasswordInput
- SearchInput
- FilterInput

### From various component files:
- CenteredInput
- CenteredCodeInput
- SecretInput
- TFACodeInput
- CodeInput
- Multiple SearchInput redefinitions (4+ instances)
