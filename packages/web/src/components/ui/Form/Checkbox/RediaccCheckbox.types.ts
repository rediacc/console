import type { CSSProperties, MouseEvent, ReactNode } from 'react';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';

export { CheckboxChangeEvent };

export interface RediaccCheckboxProps {
  /** Whether the checkbox is checked */
  checked?: boolean;
  /** Initial checked state (uncontrolled mode) */
  defaultChecked?: boolean;
  /** Disabled state */
  disabled?: boolean;
  /** Indeterminate state (partially selected) */
  indeterminate?: boolean;
  /** Change event handler */
  onChange?: (e: CheckboxChangeEvent) => void;
  /** Click event handler */
  onClick?: (e: MouseEvent<HTMLElement>) => void;
  /** Checkbox label content */
  children?: ReactNode;
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Name attribute for forms */
  name?: string;
  /** Value attribute */
  value?: string | number | boolean;
  /** Auto focus on mount */
  autoFocus?: boolean;
  /** ID attribute */
  id?: string;
}
