import { Form } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccInput, RediaccPasswordInput } from '@/components/ui';
import { focusRing } from '@/styles/mixins';
import { AlertCard, FlexRow } from '@/styles/primitives';

export const LoginContainer = styled.div`
  width: 100%;
  max-width: ${({ theme }) => theme.dimensions.CARD_WIDTH_LG}px;
`;

export const LogoContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: ${({ theme }) => theme.dimensions.HEADER_HEIGHT}px;

  img {
    height: ${({ theme }) => theme.spacing.XL}px;
    width: auto;
    max-width: ${({ theme }) => theme.dimensions.LOGO_MAX_WIDTH}px;
    object-fit: contain;
  }
`;

export const StyledAlert = styled(AlertCard).attrs({ $variant: 'error' })`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const FormLabel = styled.label`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  display: block;
`;

export const MasterPasswordLabel = styled(FormLabel)`
  display: flex;
  align-items: center;

  .anticon {
  }
`;

export const MasterPasswordFormItem = styled.div`
`;

export const AdvancedOptionsContainer = styled.div`
  text-align: center;
`;

export const AdvancedOptionsButton = styled(RediaccButton).attrs(() => ({
  variant: 'text',
  size: 'sm',
}))`
  && {
    height: auto;

    &:hover {
    }
  }
`;

export const RegisterContainer = styled.div`
  text-align: center;

  .ant-typography {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const RegisterLink = styled.a`
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  text-decoration: none;
  cursor: pointer;
  display: inline-block;

  &:hover {
  }

  &:focus-visible {
    ${focusRing('outline')}
  }
`;

export const SelectorsContainer = styled.div`
  text-align: center;

  > div:first-child {
  }
`;

export const LargeGapFormItem = styled(Form.Item)`
`;

export const NoMarginFormItem = styled(Form.Item)`
`;

export const TFAModalTitle = styled(FlexRow).attrs({})`
  .anticon {
  }
`;

export const TFACodeInput = styled(RediaccInput)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XL}px;
    letter-spacing: ${({ theme }) => theme.spacing.SM}px;
    text-align: center;
  }
`;

export const TFAButtonContainer = styled(FlexRow).attrs({ $justify: 'flex-end' })`
  width: 100%;
`;

// Use unified Form components with medium size (no wrapper needed)
export const StyledInput = RediaccInput;
export const StyledPasswordInput = RediaccPasswordInput;
