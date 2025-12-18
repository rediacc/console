import { Tabs as AntTabs } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { TabsSize, TabsVariant } from './RediaccTabs.types';

const TAB_FONT_SIZE_MAP: Record<TabsSize, keyof StyledTheme['fontSize']> = {
  sm: 'SM',
  md: 'MD',
};

export const resolveTabFontSize = (theme: StyledTheme, size: TabsSize = 'md'): number => {
  const fontSizeKey = TAB_FONT_SIZE_MAP[size] ?? 'MD';
  return theme.fontSize[fontSizeKey];
};

const VARIANT_TO_ANT_TYPE_MAP: Record<TabsVariant, 'line' | 'card' | 'editable-card'> = {
  default: 'line',
  card: 'card',
  pills: 'line', // We style pills differently via CSS
};

// Map variant to antd type
export const mapVariantToAntType = (variant: TabsVariant): 'line' | 'card' | 'editable-card' => {
  return VARIANT_TO_ANT_TYPE_MAP[variant] ?? 'line';
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

      ${({ $centered }) =>
        $centered &&
        css`
        justify-content: center;
      `}
    }

    .ant-tabs-tab {
      font-size: ${({ theme, $size }) => resolveTabFontSize(theme, $size)}px;
      padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
      color: ${({ theme }) => theme.colors.textSecondary};

      &:hover {
        color: ${({ theme }) => theme.colors.textPrimary};
      }

      ${({ $fullWidth }) =>
        $fullWidth &&
        css`
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
    ${({ $variant, theme }) =>
      $variant === 'pills' &&
      css`
      .ant-tabs-nav::before {
        display: none;
      }

      .ant-tabs-tab {
        background-color: transparent;

        &:hover {
          background-color: ${theme.colors.bgPrimary};
        }
      }

      .ant-tabs-tab-active {
        background-color: ${theme.colors.bgPrimary};
      }

      .ant-tabs-ink-bar {
        display: none;
      }
    `}

    /* Card variant */
    ${({ $variant, theme }) =>
      $variant === 'card' &&
      css`
      .ant-tabs-tab {
        background-color: ${theme.colors.bgPrimary};
      }

      .ant-tabs-tab-active {
        background-color: ${theme.colors.bgPrimary};
      }
    `}
  }
`;
