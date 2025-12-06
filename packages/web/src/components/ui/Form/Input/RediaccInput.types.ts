import type { ReactNode, ChangeEvent, CSSProperties } from 'react';

export type InputVariant = 'default';
export type InputSize = 'sm' | 'md';

export interface RediaccBaseInputProps {
  /** Visual style variant */
  variant?: InputVariant;
  /** Input size: sm (36px), md (44px) */
  size?: InputSize;
  /** Stretch to full container width */
  fullWidth?: boolean;
  /** Center text alignment */
  centered?: boolean;
  /** Placeholder text */
  placeholder?: string;
  /** Input value */
  value?: string;
  /** Change event handler */
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void;
  /** Disabled state */
  disabled?: boolean;
  /** Prefix element (icon or text) */
  prefix?: ReactNode;
  /** Suffix element (icon or text) */
  suffix?: ReactNode;
  /** Show clear button when input has value */
  allowClear?: boolean;
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Maximum length */
  maxLength?: number;
  /** Auto focus on mount */
  autoFocus?: boolean;
  /** Name attribute for forms */
  name?: string;
  /** ID attribute */
  id?: string;
  /** Blur event handler */
  onBlur?: (e: ChangeEvent<HTMLInputElement>) => void;
  /** Focus event handler */
  onFocus?: (e: ChangeEvent<HTMLInputElement>) => void;
  /** Press enter handler */
  onPressEnter?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  /** Tab index for keyboard navigation */
  tabIndex?: number;
  /** Read only state */
  readOnly?: boolean;
  /** Status (error, warning) */
  status?: 'error' | 'warning';
  /** Default value */
  defaultValue?: string;
  /** Autocomplete attribute for browser autofill */
  autoComplete?: string;
  /** Element to render after the input */
  addonAfter?: ReactNode;
  /** Element to render before the input */
  addonBefore?: ReactNode;
}

export interface RediaccInputProps extends RediaccBaseInputProps {
  /** Input type */
  type?: 'text' | 'email' | 'url' | 'tel' | 'password';
}

export interface RediaccPasswordInputProps extends Omit<RediaccBaseInputProps, 'variant' | 'type'> {
  /** Show password visibility toggle icon */
  visibilityToggle?: boolean;
  /** Custom visibility toggle icon */
  iconRender?: (visible: boolean) => ReactNode;
}

export interface RediaccTextAreaProps
  extends Omit<RediaccBaseInputProps, 'variant' | 'prefix' | 'suffix' | 'size' | 'onChange' | 'onBlur' | 'onFocus' | 'onPressEnter'> {
  /** Number of rows */
  rows?: number;
  /** Auto resize based on content */
  autoSize?: boolean | { minRows?: number; maxRows?: number };
  /** Show character count */
  showCount?: boolean;
  /** Resize behavior */
  resize?: 'none' | 'vertical' | 'horizontal' | 'both';
  /** Change event handler for textarea */
  onChange?: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  /** Blur event handler for textarea */
  onBlur?: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  /** Focus event handler for textarea */
  onFocus?: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  /** Press enter handler for textarea */
  onPressEnter?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
}

export interface RediaccInputNumberProps extends Omit<RediaccBaseInputProps, 'variant' | 'centered' | 'value' | 'defaultValue' | 'onChange'> {
  /** Minimum value */
  min?: number;
  /** Maximum value */
  max?: number;
  /** Step increment/decrement */
  step?: number | string;
  /** Precision (number of decimals) */
  precision?: number;
  /** Number formatter */
  formatter?: (value: number | string | undefined) => string;
  /** Number parser */
  parser?: (displayValue: string | undefined) => number;
  /** Change handler for number values */
  onChange?: (value: number | string | null) => void;
  /** Value as number */
  value?: number | string;
  /** Default value as number */
  defaultValue?: number | string;
  /** Show increase/decrease controls */
  controls?: boolean;
  /** Enable keyboard behavior (up/down arrows) */
  keyboard?: boolean;
}

export interface RediaccSearchInputProps extends Omit<RediaccBaseInputProps, 'variant'> {
  /** Search button action */
  onSearch?: (
    value: string,
    event?: React.ChangeEvent<HTMLInputElement> | React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLInputElement>,
    info?: { source?: 'clear' | 'input' }
  ) => void;
  /** Show search button loading state */
  loading?: boolean;
  /** Search button text or element */
  enterButton?: boolean | ReactNode;
}
