import type { CSSProperties, ReactNode } from 'react';

export interface RediaccSwitchProps {
  /** Whether the switch is checked */
  checked?: boolean;
  /** Initial checked state (uncontrolled mode) */
  defaultChecked?: boolean;
  /** Disabled state */
  disabled?: boolean;
  /** Loading state (shows spinner) */
  loading?: boolean;
  /** Change event handler */
  onChange?: (checked: boolean) => void;
  /** Size of the switch */
  size?: 'default' | 'small';
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** ID attribute */
  id?: string;
  /** Auto focus on mount */
  autoFocus?: boolean;
  /** Content when checked */
  checkedChildren?: ReactNode;
  /** Content when unchecked */
  unCheckedChildren?: ReactNode;
}
