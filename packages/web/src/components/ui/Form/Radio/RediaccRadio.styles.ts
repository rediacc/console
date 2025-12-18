import { Radio as AntRadio } from 'antd';
import styled from 'styled-components';
import { disabledState } from '@/styles/mixins';

const { Group: AntRadioGroup, Button: AntRadioButton } = AntRadio;

/**
 * Styled Rediacc Radio Group component
 *
 * Theme-aware radio button group with consistent styling.
 */
export const StyledRediaccRadioGroup = styled(AntRadioGroup)`
  && {
    display: inline-flex;

    /* Radio button styles within group */
    .ant-radio-button-wrapper {
      font-size: ${({ theme }) => theme.fontSize.SM}px;

      &:hover {
      }
    }

    /* Checked state */
    .ant-radio-button-wrapper-checked:not(.ant-radio-button-wrapper-disabled) {
      &::before {
      }

      &:hover {
      }
    }

    /* Disabled state */
    .ant-radio-button-wrapper-disabled {
      ${disabledState}
    }

    /* Focus state */
    .ant-radio-button-wrapper:focus-within {
    }
  }
`;

/**
 * Styled Rediacc Radio Button component
 *
 * Individual radio button for use within RediaccRadio.Group.
 */
export const StyledRediaccRadioButton = styled(AntRadioButton)`
  && {
    /* Base styles are handled by the group */
  }
`;
