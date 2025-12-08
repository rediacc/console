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

const getIconSize = (size: IconSize, theme: DefaultTheme) => {
  switch (size) {
    case 'sm':
      return `${theme.dimensions.ICON_SM}px`;
    case 'lg':
      return `${theme.dimensions.ICON_LG}px`;
    default:
      return `${theme.dimensions.ICON_MD}px`;
  }
};

const getIconColor = (tone: IconTone, theme: DefaultTheme) => {
  switch (tone) {
    case 'success':
      return theme.colors.success;
    case 'warning':
      return theme.colors.warning;
    case 'danger':
      return theme.colors.error;
    case 'info':
      return theme.colors.info;
    case 'muted':
      return theme.colors.textSecondary;
    case 'inherit':
      return 'currentColor';
    case 'primary':
    default:
      return theme.colors.primary;
  }
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
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`;

export const CenteredState = styled.div`
  width: 100%;
  text-align: center;
  padding: ${({ theme }) => theme.spacing.XXXL}px 0;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const CenteredBlock = styled.div`
  text-align: center;
`;

export const ErrorWrapper = styled.div`
  max-width: 480px;
  margin: 0 auto;
  width: 100%;
`;

export const LoadingState = PrimitiveLoadingState;

export const RegionsSection = styled.section`
  margin-top: ${({ theme }) => theme.spacing.XXXL}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`;
