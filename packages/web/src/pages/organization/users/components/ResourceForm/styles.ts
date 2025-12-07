import { Form } from 'antd';
import styled from 'styled-components';
import { RediaccInput, RediaccPasswordInput, RediaccSelect, RediaccStack } from '@/components/ui';

export const StyledForm = styled(Form)`
  width: 100%;
`;

export const TextInput = styled(RediaccInput)`
  && {
    width: 100%;
  }
`;

export const PasswordInput = styled(RediaccPasswordInput)`
  && {
    width: 100%;
  }
`;

export const FieldSelect = styled(RediaccSelect)`
  && {
    width: 100%;
  }
`;

export const FormActions = styled(Form.Item)`
  margin-top: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px;
  margin-bottom: 0;
`;

export const ActionButtons = styled(RediaccStack).attrs({ direction: 'horizontal' })`
  width: 100%;
  justify-content: flex-end;
`;
