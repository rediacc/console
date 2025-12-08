import type { CSSProperties, ReactNode } from 'react';

export type SelectSize = 'sm' | 'md' | 'lg';

export interface RediaccSelectOption<T = string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface RediaccSelectProps<T = any> {
  /** Select size: sm (28px), md (32px), lg (40px) */
  size?: SelectSize;
  /** Stretch to full container width */
  fullWidth?: boolean;
  /** Minimum width in pixels */
  minWidth?: number;
  /** Selected value */
  value?: T;
  /** Change handler */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onChange?: (value: T, option?: any) => void;
  /** Select options */
  options?: Array<RediaccSelectOption<T>>;
  /** Placeholder text */
  placeholder?: string;
  /** Disabled state */
  disabled?: boolean;
  /** Loading state */
  loading?: boolean;
  /** Show clear button */
  allowClear?: boolean;
  /** Enable search functionality */
  showSearch?: boolean;
  /** Custom filter function or boolean to enable/disable filtering */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  filterOption?: boolean | ((input: string, option: any) => boolean);
  /** Controlled search value */
  searchValue?: string;
  /** Search change handler */
  onSearch?: (value: string) => void;
  /** Multiple selection mode */
  mode?: 'multiple' | 'tags';
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Custom dropdown render */
  dropdownRender?: (menu: React.ReactElement) => React.ReactElement;
  /** Popup container selector */
  getPopupContainer?: (triggerNode: HTMLElement) => HTMLElement;
  /** Maximum tag count for multiple mode */
  maxTagCount?: number | 'responsive';
  /** Option filter property */
  optionFilterProp?: string;
  /** Callback when dropdown visibility changes */
  onDropdownVisibleChange?: (open: boolean) => void;
  /** Custom option label prop */
  optionLabelProp?: string;
  /** Virtual scrolling */
  virtual?: boolean;
  /** Status (error state) */
  status?: 'error' | 'warning';
  /** Custom content when no results */
  notFoundContent?: ReactNode;
  /** Custom suffix icon */
  suffixIcon?: ReactNode;
  /** Whether dropdown width matches select width */
  popupMatchSelectWidth?: boolean;
  /** Custom placeholder for hidden tags in multiple mode */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  maxTagPlaceholder?: ReactNode | ((omittedValues: any[]) => ReactNode);
  /** Inline styles */
  style?: CSSProperties;
  /** Children (for custom options) */
  children?: ReactNode;
  /** Custom tag render function for multiple mode */
  tagRender?: (props: {
    label: ReactNode;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    value: any;
    closable: boolean;
    onClose: () => void;
  }) => React.ReactElement;
}
