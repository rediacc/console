import styled from 'styled-components';
import { Form, Divider, Alert, InputNumber, Select } from 'antd';
import { FullWidthSelect as PrimitiveFullWidthSelect } from '@/styles/primitives';

export const FormWrapper = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  height: 100%;
`;

export const StyledForm = styled(Form)`
  flex-shrink: 0;
`;

export const SectionDivider = styled(Divider)`
  margin: ${({ theme }) => `${theme.spacing.SM}px 0`};
`;

export const VaultSection = styled.div`
  flex-shrink: 0;
`;

export const ImportExportRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: ${({ theme }) => theme.spacing.MD}px;
  border-top: 1px solid var(--color-border-secondary);
`;

export const DefaultsWrapper = styled.div`
  border-top: 1px solid var(--color-border-secondary);
  padding-top: ${({ theme }) => theme.spacing.MD}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const DefaultsAlert = styled(Alert)`
  margin: 0;
`;

export const SizeInputGroup = styled.div`
  display: flex;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const SizeNumberInput = styled(InputNumber)`
  && {
    flex: 0 0 65%;
  }
`;

export const SizeUnitSelect = styled(Select)`
  && {
    flex: 0 0 35%;
  }
`;

export const FullWidthSelect = PrimitiveFullWidthSelect;
