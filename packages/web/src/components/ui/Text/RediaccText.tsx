import { forwardRef } from 'react';
import { StyledRediaccText } from './RediaccText.styles';
import type { RediaccTextProps } from './RediaccText.types';

/**
 * Unified Text Component
 *
 * A single, centralized text component with the caption variant.
 *
 * @example
 * // Caption text
 * <RediaccText variant="caption">Last updated 5 minutes ago</RediaccText>
 *
 * // Default text (no variant)
 * <RediaccText>Default body text</RediaccText>
 *
 * // With overrides
 * <RediaccText size="large" weight="semibold">
 *   Custom styling
 * </RediaccText>
 *
 * // Truncated text
 * <RediaccText truncate>
 *   This is a very long text that will be truncated with ellipsis
 * </RediaccText>
 *
 * // Multi-line truncation
 * <RediaccText truncate maxLines={3}>
 *   This text will be truncated after 3 lines
 * </RediaccText>
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const RediaccText = forwardRef<any, RediaccTextProps>(
  (
    {
      variant,
      size,
      weight,
      muted,
      color,
      align,
      truncate = false,
      maxLines,
      code = false,
      as = 'span',
      children,
      className,
      style,
      onClick,
      copyable,
      ellipsis,
      ...rest
    },
    ref
  ) => {
    // Handle legacy muted prop
    const resolvedColor = muted ? 'muted' : color;

    return (
      <StyledRediaccText
        ref={ref}
        $variant={variant}
        $size={size}
        $weight={weight}
        $color={resolvedColor}
        $align={align}
        $truncate={truncate}
        $maxLines={maxLines}
        $code={code}
        $as={as}
        className={className}
        style={style}
        onClick={onClick}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        copyable={copyable as any}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ellipsis={ellipsis as any}
        {...rest}
      >
        {children}
      </StyledRediaccText>
    );
  }
);

RediaccText.displayName = 'RediaccText';
