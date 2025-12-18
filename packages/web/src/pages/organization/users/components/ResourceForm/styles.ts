import { Form } from 'antd';
import styled from 'styled-components';
import { RediaccInput, RediaccPasswordInput, RediaccSelect } from '@/components/ui';

export const StyledForm = styled(Form)`
  width: 100%;
`;

export const TextInput = styled(RediaccInput).attrs({ fullWidth: true })``;

export const PasswordInput = styled(RediaccPasswordInput).attrs({ fullWidth: true })``;

export const FieldSelect = styled(RediaccSelect).attrs({ fullWidth: true })``;

export const FormActions = styled(Form.Item)`
`;
