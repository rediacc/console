import { Divider as AntDivider } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { DividerOrientation, DividerSpacing } from './RediaccDivider.types';

const DIVIDER_SPACING_MAP: Record<DividerSpacing, number | keyof StyledTheme['spacing']> = {
  none: 0,
  sm: 'SM', // 8px
  md: 'MD', // 16px
  lg: 'LG', // 24px
};

export const resolveDividerSpacing = (
  theme: StyledTheme,
  spacing: DividerSpacing = 'md'
): number => {
  const spacingValue = DIVIDER_SPACING_MAP[spacing] ?? 'MD';
  return typeof spacingValue === 'number' ? spacingValue : theme.spacing[spacingValue];
};

export const StyledRediaccDivider = styled(AntDivider).withConfig({
  shouldForwardProp: (prop) => !['$orientation', '$spacing'].includes(prop),
})<{
  $orientation: DividerOrientation;
  $spacing: DividerSpacing;
}>`
  && {
    border-color: ${({ theme }) => theme.colors.borderSecondary};

    /* Horizontal divider margins */
    ${({ $orientation, theme, $spacing }) =>
      $orientation === 'horizontal' &&
      `
      margin: ${resolveDividerSpacing(theme, $spacing)}px 0;
    `}

    /* Vertical divider margins */
    ${({ $orientation, theme, $spacing }) =>
      $orientation === 'vertical' &&
      `
      margin: 0 ${resolveDividerSpacing(theme, $spacing)}px;
      height: auto;
      align-self: stretch;
    `}

    /* Text styling */
    .ant-divider-inner-text {
      color: ${({ theme }) => theme.colors.textSecondary};
      font-size: ${({ theme }) => theme.fontSize.SM}px;
    }
  }
`;
