import { Form, Steps, Typography } from 'antd';
import styled from 'styled-components';
import { RediaccInput, RediaccText } from '@/components/ui';
import { BaseModal, FlexRow } from '@/styles/primitives';

const { Title } = Typography;

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
  }
`;

export const FormField = styled(Form.Item)<{ $noMargin?: boolean }>`
  && {
  }
`;

// Use FlexRow from primitives
export const TermsRow = styled(FlexRow).attrs({ $align: 'flex-start', $wrap: true })`
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
    font-size: ${({ theme }) => theme.fontSize.XL}px;
    letter-spacing: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const SuccessContainer = styled.div`
  text-align: center;
`;

export const SuccessIcon = styled.span`
  display: inline-flex;
  font-size: ${({ theme }) => theme.dimensions.ICON_XXXL}px;
`;

export const SuccessTitle = styled(Title).attrs({ level: 4 })`
  && {
  }
`;

export const SuccessDescription = styled(RediaccText)`
  && {
  }
`;

export const StepsWrapper = styled(Steps)`
  && {
  }
`;
