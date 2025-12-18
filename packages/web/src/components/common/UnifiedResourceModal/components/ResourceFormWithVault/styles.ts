import { Form, InputNumber } from 'antd';
import styled from 'styled-components';
import { FlexBetween } from '@/components/common/styled';
import { RediaccAlert, RediaccSelect } from '@/components/ui';
import { FlexColumn, FlexRow } from '@/styles/primitives';

export const FormWrapper = styled(FlexColumn).attrs({})`
  height: 100%;
`;

export const StyledForm = styled(Form)`
  flex-shrink: 0;
`;

export const VaultSection = styled.div`
  flex-shrink: 0;
`;

export const ImportExportRow = styled(FlexBetween)`
`;

export const DefaultsWrapper = styled.div`
`;

export const DefaultsAlert = styled(RediaccAlert)`
`;

export const SizeInputGroup = styled(FlexRow).attrs({})`
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
