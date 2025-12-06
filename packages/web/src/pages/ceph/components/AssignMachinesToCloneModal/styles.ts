import styled from 'styled-components';
import {
  BaseModal,
  BaseTable,
  FlexColumn,
  ModalContentStack,
  ModalTitleRow,
  PaddedEmpty,
  AlertCard,
} from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';
import { RediaccSelect as UISelect, RediaccTag, RediaccText as Text } from '@/components/ui';
import { ModalSize } from '@/types/modal';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} assign-clone-machines-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

export const CloneTag = styled(RediaccTag).attrs({
  variant: 'warning',
  size: 'md',
  borderless: true,
})``;

const TabStack = styled(ModalContentStack)`
  width: 100%;
`;

export const AssignTabContainer = TabStack;
export const ManageTabContainer = TabStack;

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``;
export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })``;

export const FieldGroup = styled(FlexColumn).attrs({ $gap: 'XS' })``;

export const FieldLabel = styled(Text).attrs({
  weight: 'medium',
  size: 'sm',
})``;

export const StyledSelect = styled(UISelect).attrs({ size: 'sm' })``;

export const EmptyState = styled(PaddedEmpty)`
  margin-top: ${({ theme }) => theme.spacing.XL}px;
`;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const MachineNameText = styled(Text).attrs({
  weight: 'medium',
})``;

export const BridgeTag = styled(RediaccTag).attrs({
  preset: 'bridge',
  size: 'sm',
  borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const SelectionCount = styled(Text).attrs({
  variant: 'caption',
  color: 'muted',
})``;
