import type { ReactNode } from 'react';
import type { ButtonVariant } from '../Button/RediaccButton.types';

export interface ActionMenuItem<T = unknown> {
  /** Unique key for the menu item */
  key: string;

  /** Display label */
  label: ReactNode;

  /** Icon component */
  icon?: ReactNode;

  /** Danger styling (red) */
  danger?: boolean;

  /** Disabled state - can be boolean or function receiving record */
  disabled?: boolean | ((record: T) => boolean);

  /** Visible state - can be boolean or function receiving record */
  visible?: boolean | ((record: T) => boolean);

  /** Click handler with record context */
  onClick: (record: T) => void;

  /** Optional divider after this item */
  dividerAfter?: boolean;
}

export interface RediaccActionMenuProps<T = unknown> {
  /** Current row record (passed to onClick handlers) */
  record: T;

  /** Menu item configurations */
  items: ActionMenuItem<T>[];

  /** Custom trigger icon (defaults to MoreOutlined) */
  icon?: ReactNode;

  /** Button label text (optional, for labeled button) */
  label?: ReactNode;

  /** Button variant */
  buttonVariant?: ButtonVariant;

  /** Disabled state for entire menu */
  disabled?: boolean;

  /** Loading state */
  loading?: boolean;

  /** Dropdown placement */
  placement?: 'bottomLeft' | 'bottomRight' | 'topLeft' | 'topRight';

  /** Test identifier prefix (generates {prefix}-action-menu and {prefix}-menu-{key}) */
  testIdPrefix?: string;

  /** Tooltip text for trigger button */
  tooltip?: string;

  /** Aria label for accessibility */
  'aria-label'?: string;
}
