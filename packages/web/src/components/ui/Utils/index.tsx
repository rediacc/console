/**
 * Utility components
 *
 * General-purpose layout utilities:
 * - IconWrapper: Icon container with sizing
 * - RightAlign, CenteredState, CenteredBlock, ErrorWrapper
 * - LoadingState: Flexible loading state container
 * - RegionsSection: Special section for infrastructure page
 */

import styled, { type DefaultTheme } from 'styled-components';
import { LoadingState as PrimitiveLoadingState } from '@/styles/primitives';

type IconSize = 'sm' | 'md' | 'lg';
type IconTone = 'primary' | 'inherit' | 'success' | 'warning' | 'danger' | 'info' | 'muted';

const ICON_SIZE_MAP: Record<IconSize, keyof DefaultTheme['dimensions']> = {
  sm: 'ICON_SM',
  md: 'ICON_MD',
  lg: 'ICON_LG',
};

const getIconSize = (size: IconSize, theme: DefaultTheme) => {
  const sizeKey = ICON_SIZE_MAP[size] ?? 'ICON_MD';
  return `${theme.dimensions[sizeKey]}px`;
};

const ICON_COLOR_MAP: Record<IconTone, string> = {
  primary: 'primary',
  inherit: 'currentColor',
  success: 'success',
  warning: 'warning',
  danger: 'error',
  info: 'info',
  muted: 'textSecondary',
};

const getIconColor = (tone: IconTone, theme: DefaultTheme) => {
  const colorValue = ICON_COLOR_MAP[tone] ?? 'primary';
  return colorValue === 'currentColor'
    ? colorValue
    : theme.colors[colorValue as keyof DefaultTheme['colors']];
};

/**
 * IconWrapper - Wrapper for icons with consistent sizing
 */
export const IconWrapper = styled.span<{
  $size?: IconSize;
  $tone?: IconTone;
  $color?: string;
}>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size = 'md' }) => getIconSize($size, theme)};
  color: ${({ theme, $tone = 'primary', $color }) => $color ?? getIconColor($tone, theme)};
`;

export const RightAlign = styled.div`
  width: 100%;
  display: flex;
  justify-content: flex-end;
  text-align: right;
  flex-wrap: wrap;
`;

export const CenteredState = styled.div`
  width: 100%;
  text-align: center;
  padding: ${({ theme }) => theme.spacing.XXXL}px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const CenteredBlock = styled.div`
  text-align: center;
`;

export const ErrorWrapper = styled.div`
  max-width: ${({ theme }) => theme.dimensions.ERROR_WRAPPER_WIDTH}px;
  width: 100%;
`;

export const LoadingState = PrimitiveLoadingState;

export const RegionsSection = styled.section`
  display: flex;
  flex-direction: column;
`;
