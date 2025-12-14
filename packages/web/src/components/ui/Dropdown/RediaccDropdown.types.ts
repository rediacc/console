import type { CSSProperties, ReactElement, ReactNode } from 'react';
import type { MenuProps } from 'antd';

export type DropdownTrigger = 'click' | 'hover' | 'contextMenu';

export type DropdownPlacement =
  | 'topLeft'
  | 'topCenter'
  | 'topRight'
  | 'bottomLeft'
  | 'bottomCenter'
  | 'bottomRight';

export interface RediaccDropdownProps {
  /** Menu configuration (standard Ant pattern) */
  menu?: MenuProps;

  /** Custom popup render (for complex content like UserMenu) */
  popupRender?: (originNode: ReactNode) => ReactNode;

  /** Trigger action(s) for showing dropdown */
  trigger?: DropdownTrigger[];

  /** Dropdown placement */
  placement?: DropdownPlacement;

  /** Disabled state */
  disabled?: boolean;

  /** Whether dropdown is visible (controlled) */
  open?: boolean;

  /** Callback when visibility changes */
  onOpenChange?: (open: boolean) => void;

  /** Overlay/popup styles */
  overlayStyle?: CSSProperties;

  /** Overlay class name */
  overlayClassName?: string;

  /** Auto-adjust placement when overflow */
  autoAdjustOverflow?: boolean;

  /** Arrow visibility */
  arrow?: boolean | { pointAtCenter: boolean };

  /** Test identifier */
  'data-testid'?: string;

  /** Children (trigger element) */
  children: ReactElement;

  /** Get popup container */
  getPopupContainer?: (triggerNode: HTMLElement) => HTMLElement;

  /** Destroy popup on hide */
  destroyPopupOnHide?: boolean;
}
