import { forwardRef } from 'react';
import { StyledRediaccRadioGroup, StyledRediaccRadioButton } from './RediaccRadio.styles';
import type { RediaccRadioGroupProps, RediaccRadioButtonProps } from './RediaccRadio.types';

/**
 * Rediacc Radio Button Component
 *
 * Individual radio button for use within RediaccRadio.Group.
 *
 * @example
 * <RediaccRadio.Group value={value} onChange={handleChange}>
 *   <RediaccRadio.Button value="a">Option A</RediaccRadio.Button>
 *   <RediaccRadio.Button value="b">Option B</RediaccRadio.Button>
 * </RediaccRadio.Group>
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const RediaccRadioButton = forwardRef<any, RediaccRadioButtonProps>(
  (
    { value, disabled = false, children, className, style, 'data-testid': dataTestId, ...rest },
    ref
  ) => {
    return (
      <StyledRediaccRadioButton
        ref={ref}
        value={value}
        disabled={disabled}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      >
        {children}
      </StyledRediaccRadioButton>
    );
  }
);

RediaccRadioButton.displayName = 'RediaccRadioButton';

/**
 * Rediacc Radio Group Component
 *
 * Container for radio button options. Use RediaccRadio.Button for individual options.
 *
 * @example
 * // Basic toggle group
 * <RediaccRadio.Group value={viewMode} onChange={(e) => setViewMode(e.target.value)}>
 *   <RediaccRadio.Button value="list">List</RediaccRadio.Button>
 *   <RediaccRadio.Button value="grid">Grid</RediaccRadio.Button>
 * </RediaccRadio.Group>
 *
 * // OS selector
 * <RediaccRadio.Group value={os} onChange={handleOsChange}>
 *   <RediaccRadio.Button value="unix">
 *     <AppleOutlined /> Unix/Mac
 *   </RediaccRadio.Button>
 *   <RediaccRadio.Button value="windows">
 *     <WindowsOutlined /> Windows
 *   </RediaccRadio.Button>
 * </RediaccRadio.Group>
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const RediaccRadioGroup = forwardRef<any, RediaccRadioGroupProps>(
  (
    {
      value,
      defaultValue,
      onChange,
      disabled = false,
      children,
      className,
      style,
      name,
      id,
      size,
      buttonStyle,
      optionType,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccRadioGroup
        ref={ref}
        value={value}
        defaultValue={defaultValue}
        onChange={onChange}
        disabled={disabled}
        name={name}
        id={id}
        size={size}
        buttonStyle={buttonStyle}
        optionType={optionType}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      >
        {children}
      </StyledRediaccRadioGroup>
    );
  }
);

RediaccRadioGroup.displayName = 'RediaccRadioGroup';

/**
 * RediaccRadio Component Namespace
 *
 * Provides RediaccRadio.Group and RediaccRadio.Button for toggle-style radio selections.
 *
 * @example
 * import { RediaccRadio } from '@/components/ui/Form';
 *
 * <RediaccRadio.Group value={value} onChange={handleChange}>
 *   <RediaccRadio.Button value="option1">Option 1</RediaccRadio.Button>
 *   <RediaccRadio.Button value="option2">Option 2</RediaccRadio.Button>
 * </RediaccRadio.Group>
 */
export const RediaccRadio = {
  Group: RediaccRadioGroup,
  Button: RediaccRadioButton,
};

// Named exports for direct imports
export { RediaccRadioGroup, RediaccRadioButton };
