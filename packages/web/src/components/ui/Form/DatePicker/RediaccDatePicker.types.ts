import type { CSSProperties } from 'react';
import type { Dayjs } from 'dayjs';

export interface RediaccDatePickerProps {
  /** Selected date value */
  value?: Dayjs | null;
  /** Default date value (uncontrolled mode) */
  defaultValue?: Dayjs;
  /** Change event handler - matches antd's signature */
  onChange?: (date: unknown, dateString: string | string[] | null) => void;
  /** Disabled state */
  disabled?: boolean;
  /** Placeholder text */
  placeholder?: string;
  /** Date format string */
  format?: string;
  /** Minimum width in pixels */
  minWidth?: number;
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Allow clearing the value */
  allowClear?: boolean;
  /** Show time picker */
  showTime?: boolean;
  /** Show today button */
  showToday?: boolean;
  /** ID attribute */
  id?: string;
  /** Auto focus on mount */
  autoFocus?: boolean;
  /** Popup container */
  getPopupContainer?: (triggerNode: HTMLElement) => HTMLElement;
  /** Status (error, warning) */
  status?: 'error' | 'warning';
  /** Picker type */
  picker?: 'date' | 'week' | 'month' | 'quarter' | 'year';
  /** Disable specific dates */
  disabledDate?: (current: Dayjs) => boolean;
}

export interface RediaccRangePickerProps {
  /** Selected date range value - allows null values for individual dates */
  value?: [Dayjs | null, Dayjs | null] | null;
  /** Default date range value (uncontrolled mode) */
  defaultValue?: [Dayjs, Dayjs];
  /** Change event handler - matches antd's signature */
  onChange?: (dates: [Dayjs | null, Dayjs | null] | null, dateStrings: [string, string]) => void;
  /** Disabled state */
  disabled?: boolean;
  /** Placeholder text for start and end */
  placeholder?: [string, string];
  /** Date format string */
  format?: string;
  /** Minimum width in pixels */
  minWidth?: number;
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Allow clearing the value */
  allowClear?: boolean;
  /** Show time picker */
  showTime?: boolean;
  /** ID attribute */
  id?: string;
  /** Auto focus on mount */
  autoFocus?: boolean;
  /** Popup container */
  getPopupContainer?: (triggerNode: HTMLElement) => HTMLElement;
  /** Status (error, warning) */
  status?: 'error' | 'warning';
  /** Picker type */
  picker?: 'date' | 'week' | 'month' | 'quarter' | 'year';
  /** Disable specific dates */
  disabledDate?: (current: Dayjs) => boolean;
  /** Separator between start and end */
  separator?: React.ReactNode;
}
