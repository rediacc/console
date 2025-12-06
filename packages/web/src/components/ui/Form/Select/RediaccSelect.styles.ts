import styled, { css } from 'styled-components';
import { Select as AntSelect } from 'antd';
import type { StyledTheme } from '@/styles/styledTheme';
import type { SelectSize } from './RediaccSelect.types';

/**
 * Resolves height for each select size
 */
export const resolveSelectHeight = (theme: StyledTheme, size: SelectSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.dimensions.CONTROL_HEIGHT_SM; // 28px
    case 'lg':
      return theme.dimensions.CONTROL_HEIGHT_LG; // 40px
    case 'md':
    default:
      return theme.dimensions.CONTROL_HEIGHT; // 32px
  }
};

/**
 * Unified RediaccSelect styled component
 */
export const StyledRediaccSelect = styled(AntSelect).withConfig({
  shouldForwardProp: (prop) => !['$size', '$fullWidth', '$minWidth'].includes(prop),
})<{
  $size: SelectSize;
  $fullWidth?: boolean;
  $minWidth?: number;
}>`
  &.ant-select {
    /* Width modifiers */
    ${({ $fullWidth }) =>
      $fullWidth &&
      css`
        width: 100%;
      `}

    ${({ $minWidth }) =>
      $minWidth &&
      css`
        min-width: ${$minWidth}px;
      `}

    /* Selector styling */
    .ant-select-selector {
      min-height: ${({ theme, $size }) => resolveSelectHeight(theme, $size)}px;
      border-radius: ${({ theme }) => theme.borderRadius.MD}px;
      background-color: ${({ theme }) => theme.colors.inputBg};
      border-color: ${({ theme }) => theme.colors.inputBorder};
      padding: 0 ${({ theme }) => theme.spacing.SM}px;
      transition: ${({ theme }) => theme.transitions.DEFAULT};

      /* Ensure proper vertical centering */
      display: flex;
      align-items: center;

      /* Selection items (for tags/multiple mode) */
      .ant-select-selection-item {
        display: inline-flex;
        align-items: center;
        height: ${({ theme, $size }) => {
          const height = resolveSelectHeight(theme, $size);
          return height - 8;
        }}px;
        line-height: 1.2;
        margin: 2px 4px 2px 0;
        padding: 0 ${({ theme }) => theme.spacing.XS}px;
        border-radius: ${({ theme }) => theme.borderRadius.SM}px;
        background-color: ${({ theme }) => theme.colors.bgSecondary};
        border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
      }

      /* Selected value text */
      .ant-select-selection-search {
        display: flex;
        align-items: center;
      }

      .ant-select-selection-placeholder {
        display: flex;
        align-items: center;
        color: ${({ theme }) => theme.colors.textTertiary};
      }
    }

    /* Focus state */
    &.ant-select-focused .ant-select-selector {
      border-color: ${({ theme }) => theme.colors.primary};
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
      outline: none;
    }

    /* Error state */
    &.ant-select-status-error .ant-select-selector {
      border-color: ${({ theme }) => theme.colors.error};
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.error};
    }

    /* Warning state */
    &.ant-select-status-warning .ant-select-selector {
      border-color: ${({ theme }) => theme.colors.warning};
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.warning};
    }

    /* Disabled state */
    &.ant-select-disabled .ant-select-selector {
      background-color: ${({ theme }) => theme.colors.bgSecondary};
      color: ${({ theme }) => theme.colors.textTertiary};
      cursor: not-allowed;
      opacity: 0.6;
    }

    /* Arrow icon */
    .ant-select-arrow {
      color: ${({ theme }) => theme.colors.textTertiary};
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
      transition: ${({ theme }) => theme.transitions.FAST};

      .anticon {
        display: flex;
        align-items: center;
        justify-content: center;
      }
    }

    &.ant-select-focused .ant-select-arrow,
    &:hover .ant-select-arrow {
      color: ${({ theme }) => theme.colors.primary};
    }

    /* Clear icon */
    .ant-select-clear {
      background-color: ${({ theme }) => theme.colors.bgPrimary};
      color: ${({ theme }) => theme.colors.textTertiary};
      opacity: 0.6;
      transition: ${({ theme }) => theme.transitions.FAST};

      &:hover {
        opacity: 1;
        color: ${({ theme }) => theme.colors.textSecondary};
      }
    }
  }
`;
