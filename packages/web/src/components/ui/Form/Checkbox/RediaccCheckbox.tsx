import { forwardRef } from 'react';
import { StyledRediaccCheckbox } from './RediaccCheckbox.styles';
import type { RediaccCheckboxProps } from './RediaccCheckbox.types';

/**
 * Unified RediaccCheckbox Component
 *
 * A theme-aware checkbox component that replaces direct antd imports.
 *
 * @example
 * // Basic checkbox
 * <RediaccCheckbox>Accept terms</RediaccCheckbox>
 *
 * // Controlled checkbox
 * <RediaccCheckbox checked={isChecked} onChange={(e) => setIsChecked(e.target.checked)}>
 *   Remember me
 * </RediaccCheckbox>
 *
 * // Indeterminate state (for "select all" functionality)
 * <RediaccCheckbox indeterminate={someSelected} checked={allSelected} onChange={handleSelectAll}>
 *   Select all
 * </RediaccCheckbox>
 *
 * // Disabled checkbox
 * <RediaccCheckbox disabled>Can't change this</RediaccCheckbox>
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccCheckbox = forwardRef<any, RediaccCheckboxProps>(
  (
    {
      checked,
      defaultChecked,
      disabled = false,
      indeterminate = false,
      onChange,
      onClick,
      children,
      name,
      value,
      autoFocus = false,
      id,
      className,
      style,
      'data-testid': dataTestId,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccCheckbox
        ref={ref}
        checked={checked}
        defaultChecked={defaultChecked}
        disabled={disabled}
        indeterminate={indeterminate}
        onChange={onChange}
        onClick={onClick}
        name={name}
        value={value}
        autoFocus={autoFocus}
        id={id}
        className={className}
        style={style}
        data-testid={dataTestId}
        {...rest}
      >
        {children}
      </StyledRediaccCheckbox>
    );
  }
);

RediaccCheckbox.displayName = 'RediaccCheckbox';
