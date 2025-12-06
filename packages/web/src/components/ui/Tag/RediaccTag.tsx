import { forwardRef } from 'react';
import { StyledRediaccTag } from './RediaccTag.styles';
import type { RediaccTagProps, TagPreset, TagVariant } from './RediaccTag.types';

/**
 * Map semantic presets to visual variants
 */
const presetVariantMap: Record<TagPreset, TagVariant> = {
  team: 'success',
  machine: 'primary',
  bridge: 'secondary',
  region: 'neutral',
};

/**
 * Unified Tag Component
 *
 * A centralized tag component that provides consistent styling for labels,
 * badges, and categorical indicators throughout the application.
 *
 * @example
 * // Basic tag
 * <RediaccTag variant="primary">Active</RediaccTag>
 *
 * // Status tag
 * <RediaccTag variant="success">Online</RediaccTag>
 *
 * // Semantic preset
 * <RediaccTag preset="team">Production</RediaccTag>
 *
 * // With icon
 * <RediaccTag variant="info" icon={<InfoCircleOutlined />}>Info</RediaccTag>
 *
 * // Borderless tag
 * <RediaccTag preset="machine" borderless>server-01</RediaccTag>
 *
 * // Closable tag
 * <RediaccTag variant="warning" closable onClose={() => console.log('closed')}>
 *   Warning
 * </RediaccTag>
 *
 * // Different sizes
 * <RediaccTag size="small">Small</RediaccTag>
 * <RediaccTag size="md">Medium</RediaccTag>
 * <RediaccTag size="large">Large</RediaccTag>
 */
export const RediaccTag = forwardRef<HTMLSpanElement, RediaccTagProps>(
  (
    {
      variant = 'default',
      size = 'md',
      preset,
      borderless = false,
      icon,
      closable = false,
      onClose,
      children,
      ...rest
    },
    ref
  ) => {
    // Resolve variant from preset if provided
    const resolvedVariant = preset ? presetVariantMap[preset] : variant;

    return (
      <StyledRediaccTag
        ref={ref}
        $variant={resolvedVariant}
        $size={size}
        $borderless={borderless}
        closable={closable}
        onClose={onClose}
        icon={icon}
        {...rest}
      >
        {children}
      </StyledRediaccTag>
    );
  }
);

RediaccTag.displayName = 'RediaccTag';
