import type { ReactNode, CSSProperties } from 'react';
import type { RadioChangeEvent } from 'antd';

export { RadioChangeEvent };

export interface RediaccRadioButtonProps {
  /** Button value */
  value?: any;
  /** Disabled state */
  disabled?: boolean;
  /** Button label content */
  children?: ReactNode;
  /** Test identifier */
  'data-testid'?: string;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
}

export interface RediaccRadioGroupProps {
  /** Selected value */
  value?: any;
  /** Default selected value (uncontrolled mode) */
  defaultValue?: any;
  /** Change event handler */
  onChange?: (e: RadioChangeEvent) => void;
  /** Disabled state for all buttons */
  disabled?: boolean;
  /** Radio button children */
  children?: ReactNode;
  /** Additional class name */
  className?: string;
  /** Inline styles */
  style?: CSSProperties;
  /** Test identifier */
  'data-testid'?: string;
  /** Name attribute for form */
  name?: string;
  /** ID attribute */
  id?: string;
  /** Size of the buttons */
  size?: 'large' | 'middle' | 'small';
  /** Style type */
  buttonStyle?: 'outline' | 'solid';
  /** Option style type */
  optionType?: 'default' | 'button';
}
