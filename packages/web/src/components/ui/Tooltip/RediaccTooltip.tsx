import { forwardRef } from 'react';
import { Tooltip as AntTooltip } from 'antd';
import { useTheme } from 'styled-components';
import { colorTokens } from '@/config/antdTheme';
import type { StyledTheme } from '@/styles/styledTheme';
import { getTooltipOverlayStyle } from './RediaccTooltip.styles';
import type { RediaccTooltipProps } from './RediaccTooltip.types';
import type { TooltipRef } from 'antd/es/tooltip';

/**
 * Unified Tooltip Component
 *
 * A wrapper around Ant Design Tooltip with semantic variants for consistent styling.
 *
 * @example
 * // Default tooltip
 * <RediaccTooltip title="Edit item">
 *   <Button icon={<EditOutlined />} />
 * </RediaccTooltip>
 *
 * @example
 * // Warning variant
 * <RediaccTooltip title="This action cannot be undone" variant="warning">
 *   <Button danger>Delete</Button>
 * </RediaccTooltip>
 *
 * @example
 * // Error variant
 * <RediaccTooltip title="Connection failed" variant="error">
 *   <StatusIcon />
 * </RediaccTooltip>
 *
 * @example
 * // With placement
 * <RediaccTooltip title="Settings" placement="left">
 *   <SettingsIcon />
 * </RediaccTooltip>
 */
export const RediaccTooltip = forwardRef<TooltipRef, RediaccTooltipProps>(
  (
    {
      title,
      variant = 'default',
      placement,
      arrow = true,
      open,
      onOpenChange,
      trigger,
      mouseEnterDelay,
      mouseLeaveDelay,
      zIndex,
      children,
      overlayClassName,
      overlayStyle,
      overlayInnerStyle,
      ...rest
    },
    ref
  ) => {
    const theme = useTheme() as StyledTheme;

    // Determine tooltipBg based on theme mode
    const isDark = theme.colors.bgPrimary === colorTokens.dark.bgPrimary;
    const tooltipBg = isDark ? colorTokens.dark.tooltipBg : colorTokens.light.tooltipBg;

    // Get variant-specific overlay styles
    const variantOverlayStyle = getTooltipOverlayStyle(variant, theme, tooltipBg);

    // Merge with any user-provided overlayInnerStyle
    const mergedOverlayInnerStyle = {
      ...variantOverlayStyle,
      ...overlayInnerStyle,
    };

    return (
      <AntTooltip
        ref={ref}
        title={title}
        placement={placement}
        arrow={arrow}
        open={open}
        onOpenChange={onOpenChange}
        trigger={trigger}
        mouseEnterDelay={mouseEnterDelay}
        mouseLeaveDelay={mouseLeaveDelay}
        zIndex={zIndex}
        overlayClassName={overlayClassName}
        overlayStyle={overlayStyle}
        overlayInnerStyle={mergedOverlayInnerStyle}
        {...rest}
      >
        {children}
      </AntTooltip>
    );
  }
);

RediaccTooltip.displayName = 'RediaccTooltip';
