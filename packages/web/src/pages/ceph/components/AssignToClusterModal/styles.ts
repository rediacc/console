import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccSelect, RediaccTag } from '@/components/ui';
import {
  AlertCard,
  BaseModal,
  BaseTable,
  FlexColumn,
  FlexRow,
  ModalContentStack,
  ModalTitleRow,
} from '@/styles/primitives';
import { ModalSize } from '@/types/modal';

export const StyledModal = styled(BaseModal).attrs<{ $size: ModalSize }>(({ $size }) => ({
  className: `${$size} assign-to-cluster-modal`,
}))<{ $size: ModalSize }>``;

export const TitleStack = styled(ModalTitleRow)``;

export const ContentStack = styled(ModalContentStack)`
  width: 100%;
`;

export const ClusterAlert = styled(AlertCard).attrs({ $variant: 'warning' })`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const MachineDetailsSection = styled(FlexColumn).attrs({ $gap: 'SM' })``;

export const DetailRow = styled(InlineStack).attrs({ $align: 'flex-start' })`
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const FieldGroup = styled(FlexColumn).attrs({ $gap: 'XS' })``;

export const StyledSelect = RediaccSelect;

export const LoadingWrapper = styled(FlexRow).attrs({ $gap: 'SM' })``;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const TeamTag = styled(RediaccTag).attrs({
  preset: 'team',
  size: 'sm',
  borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const AssignmentTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`;
