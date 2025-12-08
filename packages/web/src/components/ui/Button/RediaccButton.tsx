import { forwardRef } from 'react';
import { StyledRediaccButton } from './RediaccButton.styles';
import type { RediaccButtonProps } from './RediaccButton.types';

/**
 * Unified Button Component
 *
 * A single, centralized button component that replaces all legacy button variants.
 * Default variant is "primary" for maximum visibility in both light and dark themes.
 *
 * @example
 * // Primary action button (default)
 * <RediaccButton>Create</RediaccButton>
 *
 * // Danger/destructive action
 * <RediaccButton variant="danger">Delete</RediaccButton>
 *
 * // Small size button
 * <RediaccButton size="small">Save</RediaccButton>
 *
 * // Icon-only button
 * <RediaccButton iconOnly icon={<EditOutlined />} aria-label="Edit" />
 *
 * // Form submit button
 * <RediaccButton htmlType="submit" loading={isSubmitting}>Submit</RediaccButton>
 *
 * // Full-width button
 * <RediaccButton fullWidth>Sign In</RediaccButton>
 */
export const RediaccButton = forwardRef<HTMLButtonElement, RediaccButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      iconOnly = false,
      square = false,
      compact = false,
      icon,
      loading = false,
      disabled = false,
      htmlType = 'button',
      onClick,
      minWidth,
      fullWidth = false,
      danger = false,
      block,
      title,
      children,
      ...rest
    },
    ref
  ) => {
    // Handle danger as variant override
    const resolvedVariant = danger ? 'danger' : variant;

    // Handle block prop as fullWidth (backwards compatibility)
    const resolvedFullWidth = fullWidth || block;

    // Handle square as alias for iconOnly
    const resolvedIconOnly = iconOnly || square;

    // Handle compact as size override
    const resolvedSize = compact ? 'sm' : size;

    return (
      <StyledRediaccButton
        ref={ref}
        $variant={resolvedVariant}
        $size={resolvedSize}
        $iconOnly={resolvedIconOnly}
        $minWidth={minWidth}
        $fullWidth={resolvedFullWidth}
        icon={icon}
        loading={loading}
        disabled={disabled || loading}
        htmlType={htmlType}
        onClick={onClick}
        title={title}
        {...rest}
      >
        {!resolvedIconOnly && children}
      </StyledRediaccButton>
    );
  }
);

RediaccButton.displayName = 'RediaccButton';
