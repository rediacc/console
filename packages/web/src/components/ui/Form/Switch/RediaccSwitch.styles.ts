import { Switch as AntSwitch } from 'antd';
import styled from 'styled-components';
import { disabledState } from '@/styles/mixins';

/**
 * Styled RediaccSwitch component
 *
 * Theme-aware toggle switch with consistent styling.
 */
export const StyledRediaccSwitch = styled(AntSwitch)`
  && {
    /* Disabled state */
    &.ant-switch-disabled {
      ${disabledState}
    }

    /* Focus state */
    &:focus-visible {
      outline: none;
    }

    /* Inner text styles */
    .ant-switch-inner {
      font-size: ${({ theme }) => theme.fontSize.XS}px;
    }
  }
`;
