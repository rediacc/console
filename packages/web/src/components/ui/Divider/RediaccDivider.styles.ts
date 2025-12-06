import styled from 'styled-components';
import { Divider as AntDivider } from 'antd';
import type { StyledTheme } from '@/styles/styledTheme';
import type { DividerOrientation, DividerSpacing } from './RediaccDivider.types';

export const resolveDividerSpacing = (theme: StyledTheme, spacing: DividerSpacing = 'md'): number => {
  switch (spacing) {
    case 'none': return 0;
    case 'sm': return theme.spacing.SM; // 8px
    case 'lg': return theme.spacing.LG; // 24px
    case 'md':
    default: return theme.spacing.MD; // 16px
  }
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
    ${({ $orientation, theme, $spacing }) => $orientation === 'horizontal' && `
      margin: ${resolveDividerSpacing(theme, $spacing)}px 0;
    `}

    /* Vertical divider margins */
    ${({ $orientation, theme, $spacing }) => $orientation === 'vertical' && `
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
