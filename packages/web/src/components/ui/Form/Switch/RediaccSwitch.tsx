import { forwardRef } from 'react';
import { StyledRediaccSwitch } from './RediaccSwitch.styles';
import type { RediaccSwitchProps } from './RediaccSwitch.types';

/**
 * Unified RediaccSwitch Component
 *
 * A theme-aware toggle switch component that replaces direct antd imports.
 *
 * @example
 * // Basic switch
 * <RediaccSwitch checked={isEnabled} onChange={setIsEnabled} />
 *
 * // With labels
 * <RediaccSwitch
 *   checked={isActive}
 *   onChange={setIsActive}
 *   checkedChildren="ON"
 *   unCheckedChildren="OFF"
 * />
 *
 * // Small size
 * <RediaccSwitch size="small" checked={value} onChange={setValue} />
 *
 * // Disabled switch
 * <RediaccSwitch disabled checked={false} />
 *
 * // Loading state
 * <RediaccSwitch loading checked={isLoading} onChange={handleToggle} />
 */
export const RediaccSwitch = forwardRef<any, RediaccSwitchProps>(
  (
    {
      checked,
      defaultChecked,
      disabled = false,
      loading = false,
      onChange,
      size = 'default',
      id,
      autoFocus = false,
      checkedChildren,
      unCheckedChildren,
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccSwitch
        ref={ref}
        checked={checked}
        defaultChecked={defaultChecked}
        disabled={disabled}
        loading={loading}
        onChange={onChange}
        size={size}
        id={id}
        autoFocus={autoFocus}
        checkedChildren={checkedChildren}
        unCheckedChildren={unCheckedChildren}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      />
    );
  }
);

RediaccSwitch.displayName = 'RediaccSwitch';
