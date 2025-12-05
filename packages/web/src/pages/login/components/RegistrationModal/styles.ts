import styled from 'styled-components';
import { Form, Space, Steps, Button, Input, Typography } from 'antd';
import { BaseModal } from '@/styles/primitives';

const { Title, Text } = Typography;

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
    padding-top: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const VerticalStack = styled(Space)`
  && {
    width: 100%;
  }
`;

export const FormField = styled(Form.Item)<{ $noMargin?: boolean }>`
  && {
    margin-bottom: ${({ theme, $noMargin }) => ($noMargin ? 0 : theme.spacing.SM)}px;
  }
`;

export const TermsRow = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.LG}px;
  align-items: flex-start;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`;

export const TermsField = styled(FormField)`
  && {
    flex: 1;
  }
`;

export const CaptchaWrapper = styled.div`
  flex: 0 0 auto;
`;

export const SubmitButton = styled(Button)`
  && {
    margin-top: ${({ theme }) => theme.spacing.XS}px;
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

export const VerificationButton = styled(SubmitButton)`
  && {
    height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  }
`;

export const CodeInput = styled(Input)`
  && {
    text-align: center;
    font-size: ${({ theme }) => theme.fontSize.H4}px;
    letter-spacing: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const SuccessContainer = styled.div`
  text-align: center;
  padding: ${({ theme }) => `${theme.spacing.XL}px 0`};
`;

export const SuccessIcon = styled.span`
  display: inline-flex;
  font-size: ${({ theme }) => theme.dimensions.ICON_XXXL}px;
  color: ${({ theme }) => theme.colors.success};
`;

export const SuccessTitle = styled(Title).attrs({ level: 4 })`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const SuccessDescription = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const StepsWrapper = styled(Steps)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;
