import { Select as AntSelect } from 'antd';
import styled, { css } from 'styled-components';
import { disabledState } from '@/styles/mixins';

/**
 * Unified RediaccSelect styled component
 */
export const StyledRediaccSelect = styled(AntSelect).withConfig({
  shouldForwardProp: (prop) => !['$fullWidth', '$minWidth'].includes(prop),
})<{
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
      min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
      padding: 0 ${({ theme }) => theme.spacing.SM}px;

      /* Ensure proper vertical centering */
      display: flex;
      align-items: center;

      /* Selection items (for tags/multiple mode) */
      .ant-select-selection-item {
        display: inline-flex;
        align-items: center;
        height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT - 8}px;
        line-height: ${({ theme }) => theme.lineHeight.TIGHT};
        padding: 0 ${({ theme }) => theme.spacing.XS}px;
      }

      /* Selected value text */
      .ant-select-selection-search {
        display: flex;
        align-items: center;
      }

      .ant-select-selection-placeholder {
        display: flex;
        align-items: center;
      }
    }

    /* Focus state */
    &.ant-select-focused .ant-select-selector {
      outline: none;
    }

    /* Error state */
    &.ant-select-status-error .ant-select-selector {
    }

    /* Warning state */
    &.ant-select-status-warning .ant-select-selector {
    }

    /* Disabled state */
    &.ant-select-disabled .ant-select-selector {
      ${disabledState}
    }

    /* Arrow icon */
    .ant-select-arrow {
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;

      .anticon {
        display: flex;
        align-items: center;
        justify-content: center;
      }
    }

    &.ant-select-focused .ant-select-arrow,
    &:hover .ant-select-arrow {
    }

    /* Clear icon */
    .ant-select-clear {
    }
  }
`;
