import { Form, Steps, Typography } from 'antd';
import styled from 'styled-components';
import { RediaccInput, RediaccText, RediaccStack } from '@/components/ui';
import { BaseModal, FlexRow } from '@/styles/primitives';

const { Title } = Typography;

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
    padding-top: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const VerticalStack = styled(RediaccStack).attrs({ direction: 'vertical' })`
  && {
    width: 100%;
  }
`;

export const FormField = styled(Form.Item)<{ $noMargin?: boolean }>`
  && {
    margin-bottom: ${({ theme, $noMargin }) => ($noMargin ? 0 : theme.spacing.SM)}px;
  }
`;

// Use FlexRow from primitives
export const TermsRow = styled(FlexRow).attrs({ $gap: 'LG', $align: 'flex-start', $wrap: true })`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const TermsField = styled(FormField)`
  && {
    flex: 1;
  }
`;

export const CaptchaWrapper = styled.div`
  flex: 0 0 auto;
`;

export const CodeInput = styled(RediaccInput).attrs({ centered: true })`
  && {
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

export const SuccessDescription = styled(RediaccText)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const StepsWrapper = styled(Steps)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;
