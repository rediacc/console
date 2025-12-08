import { Input as AntdInput, Form } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccInput, RediaccPasswordInput } from '@/components/ui';
import { focusRing } from '@/styles/mixins';
import { AlertCard, FlexRow, fadeInAnimation } from '@/styles/primitives';

export const LoginContainer = styled.div`
  width: 100%;
  max-width: ${({ theme }) => theme.dimensions.CARD_WIDTH_LG}px;
  margin: 0 auto;
  padding: ${({ theme }) => theme.spacing.LG}px;
`;

export const LogoContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: ${({ theme }) => theme.dimensions.HEADER_HEIGHT}px;
  margin-top: ${({ theme }) => theme.spacing.MD}px;

  img {
    height: ${({ theme }) => theme.spacing.XL}px;
    width: auto;
    max-width: 150px;
    object-fit: contain;
  }
`;

export const StyledAlert = styled(AlertCard).attrs({ $variant: 'error' })`
  && {
    border-width: 2px;
    box-shadow: ${({ theme }) => theme.shadows.ERROR_FIELD};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const FormLabel = styled.label`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  color: ${({ theme }) => theme.colors.textPrimary};
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  display: block;
`;

export const MasterPasswordLabel = styled(FormLabel)`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;

  .anticon {
    color: ${({ theme }) => theme.colors.textTertiary};
  }
`;

export const MasterPasswordFormItem = styled.div`
  animation: ${fadeInAnimation} 0.3s ease-out;
`;

export const AdvancedOptionsContainer = styled.div`
  text-align: center;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const AdvancedOptionsButton = styled(RediaccButton).attrs(() => ({
  variant: 'text',
  size: 'sm',
}))`
  && {
    color: ${({ theme }) => theme.colors.textTertiary};
    height: auto;
    padding: ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.spacing.SM}px;

    &:hover {
      background-color: ${({ theme }) => theme.colors.bgHover};
      color: ${({ theme }) => theme.colors.textSecondary};
    }
  }
`;

export const RegisterContainer = styled.div`
  text-align: center;
  margin-top: ${({ theme }) => theme.spacing.SM}px;

  .ant-typography {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const RegisterLink = styled.a`
  color: ${({ theme }) => theme.colors.primary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  text-decoration: none;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  padding: 4px 8px;
  margin-left: 4px;
  transition: ${({ theme }) => theme.transitions.DEFAULT};
  cursor: pointer;
  display: inline-block;

  &:hover {
    background-color: ${({ theme }) => theme.colors.primaryBg};
    color: ${({ theme }) => theme.colors.primary};
  }

  &:focus-visible {
    ${focusRing('outline')}
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }
`;

export const SelectorsContainer = styled.div`
  text-align: center;
  margin-top: ${({ theme }) => theme.spacing.LG}px;

  > div:first-child {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const LargeGapFormItem = styled(Form.Item)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const NoMarginFormItem = styled(Form.Item)`
  margin-bottom: 0;
`;

export const TFAModalTitle = styled(FlexRow).attrs({ $gap: 'SM' })`
  .anticon {
    color: ${({ theme }) => theme.colors.primary};
  }
`;

export const TFACodeInput = styled(AntdInput)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XL}px;
    letter-spacing: ${({ theme }) => theme.spacing.SM}px;
    text-align: center;
  }
`;

export const TFAButtonContainer = styled(FlexRow).attrs({ $justify: 'flex-end', $gap: 'SM' })`
  width: 100%;
`;

// Use unified Form components with medium size (no wrapper needed)
export const StyledInput = RediaccInput;
export const StyledPasswordInput = RediaccPasswordInput;
