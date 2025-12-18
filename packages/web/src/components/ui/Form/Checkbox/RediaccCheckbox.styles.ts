import { Checkbox as AntCheckbox } from 'antd';
import styled from 'styled-components';
import { disabledState } from '@/styles/mixins';

/**
 * Styled RediaccCheckbox component
 *
 * Theme-aware checkbox with consistent styling.
 */
export const StyledRediaccCheckbox = styled(AntCheckbox)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;

    /* Checkbox indicator styles */
    .ant-checkbox {
      .ant-checkbox-inner {
      }
    }

    /* Checked state */
    .ant-checkbox-checked {
      .ant-checkbox-inner {
      }
    }

    /* Indeterminate state */
    .ant-checkbox-indeterminate {
      .ant-checkbox-inner {
        &::after {
        }
      }
    }

    /* Disabled state */
    &.ant-checkbox-wrapper-disabled {
      ${disabledState}

      .ant-checkbox-disabled .ant-checkbox-inner {
      }
    }

    /* Focus state */
    .ant-checkbox-input:focus-visible + .ant-checkbox-inner {
    }
  }
`;
