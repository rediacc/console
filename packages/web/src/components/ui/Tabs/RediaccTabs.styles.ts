import styled, { css } from 'styled-components';
import { Tabs as AntTabs } from 'antd';
import type { StyledTheme } from '@/styles/styledTheme';
import type { TabsVariant, TabsSize } from './RediaccTabs.types';

export const resolveTabFontSize = (theme: StyledTheme, size: TabsSize = 'md'): number => {
  switch (size) {
    case 'sm': return theme.fontSize.SM;
    case 'md':
    default: return theme.fontSize.BASE;
  }
};

// Map variant to antd type
export const mapVariantToAntType = (variant: TabsVariant): 'line' | 'card' | 'editable-card' => {
  switch (variant) {
    case 'card': return 'card';
    case 'pills': return 'line'; // We style pills differently via CSS
    case 'default':
    default: return 'line';
  }
};

export const StyledRediaccTabs = styled(AntTabs).withConfig({
  shouldForwardProp: (prop) => !['$variant', '$size', '$centered', '$fullWidth'].includes(prop),
})<{
  $variant: TabsVariant;
  $size: TabsSize;
  $centered?: boolean;
  $fullWidth?: boolean;
}>`
  && {
    .ant-tabs-nav {
      margin-bottom: ${({ theme }) => theme.spacing.MD}px;

      ${({ $centered }) => $centered && css`
        justify-content: center;
      `}

      &::before {
        border-color: ${({ theme }) => theme.colors.borderSecondary};
      }
    }

    .ant-tabs-tab {
      font-size: ${({ theme, $size }) => resolveTabFontSize(theme, $size)}px;
      padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
      color: ${({ theme }) => theme.colors.textSecondary};
      transition: ${({ theme }) => theme.transitions.DEFAULT};

      &:hover {
        color: ${({ theme }) => theme.colors.textPrimary};
      }

      ${({ $fullWidth }) => $fullWidth && css`
        flex: 1;
        justify-content: center;
      `}
    }

    .ant-tabs-tab-active .ant-tabs-tab-btn {
      color: ${({ theme }) => theme.colors.textPrimary};
      font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    }

    .ant-tabs-ink-bar {
      background-color: ${({ theme }) => theme.colors.primary};
    }

    /* Pills variant */
    ${({ $variant, theme }) => $variant === 'pills' && css`
      .ant-tabs-nav::before {
        display: none;
      }

      .ant-tabs-tab {
        border-radius: ${theme.borderRadius.MD}px;
        background-color: transparent;
        margin: 0 ${theme.spacing.XS}px;

        &:hover {
          background-color: ${theme.colors.bgHover};
        }
      }

      .ant-tabs-tab-active {
        background-color: ${theme.colors.bgActive};
      }

      .ant-tabs-ink-bar {
        display: none;
      }
    `}

    /* Card variant */
    ${({ $variant, theme }) => $variant === 'card' && css`
      .ant-tabs-tab {
        background-color: ${theme.colors.bgSecondary};
        border: 1px solid ${theme.colors.borderSecondary};
        border-radius: ${theme.borderRadius.MD}px ${theme.borderRadius.MD}px 0 0;
        margin-right: ${theme.spacing.XS}px;
      }

      .ant-tabs-tab-active {
        background-color: ${theme.colors.bgPrimary};
        border-bottom-color: ${theme.colors.bgPrimary};
      }
    `}
  }
`;
