import { Form, InputNumber } from 'antd';
import styled from 'styled-components';
import { FlexBetween } from '@/components/common/styled';
import { RediaccAlert, RediaccSelect } from '@/components/ui';
import { FlexColumn, FlexRow } from '@/styles/primitives';

export const FormWrapper = styled(FlexColumn).attrs({ $gap: 'SM' })`
  height: 100%;
`;

export const StyledForm = styled(Form)`
  flex-shrink: 0;
`;

export const VaultSection = styled.div`
  flex-shrink: 0;
`;

export const ImportExportRow = styled(FlexBetween)`
  padding-top: ${({ theme }) => theme.spacing.MD}px;
  border-top: 1px solid var(--color-border-secondary);
`;

export const DefaultsWrapper = styled.div`
  border-top: 1px solid var(--color-border-secondary);
  padding-top: ${({ theme }) => theme.spacing.MD}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const DefaultsAlert = styled(RediaccAlert)`
  margin: 0;
`;

export const SizeInputGroup = styled(FlexRow).attrs({ $gap: 'SM' })`
  width: 100%;
`;

export const SizeNumberInput = styled(InputNumber)`
  && {
    flex: 0 0 65%;
  }
`;

export const SizeUnitSelect = styled(RediaccSelect)`
  && {
    flex: 0 0 35%;
  }
`;
