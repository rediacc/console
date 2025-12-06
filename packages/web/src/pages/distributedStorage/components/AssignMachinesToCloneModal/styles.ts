import styled from 'styled-components';
import { Button, Typography } from 'antd';
import {
  BaseModal,
  BaseTable,
  FlexColumn,
  ModalContentStack,
  ModalTitleRow,
  PaddedEmpty,
  PillTag,
  FormLabel,
  AlertCard,
} from '@/styles/primitives';
import { InlineStack, ModalSelect } from '@/components/common/styled';
import { ModalSize } from '@/types/modal';

const { Text } = Typography;

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} assign-clone-machines-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

export const CloneTag = styled(PillTag).attrs({
  $variant: 'warning',
  $size: 'MD',
  $borderless: true,
})``;

const TabStack = styled(ModalContentStack)`
  width: 100%;
`;

export const AssignTabContainer = TabStack;
export const ManageTabContainer = TabStack;

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``;
export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })``;

export const FieldGroup = styled(FlexColumn).attrs({ $gap: 'XS' })``;

export const FieldLabel = FormLabel;

export const StyledSelect = styled(ModalSelect).attrs({ $compact: true })``;

export const EmptyState = styled(PaddedEmpty)`
  margin-top: ${({ theme }) => theme.spacing.XL}px;
`;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const MachineNameText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const BridgeTag = styled(PillTag).attrs({
  $variant: 'success',
  $size: 'SM',
  $borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const SelectionCount = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const FooterButton = styled(Button)`
  min-width: 120px;
`;
