import styled from 'styled-components';
import { BaseModal, BaseTable, ModalTitleRow, AlertCard } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag, RediaccText as Text } from '@/components/ui';
import { WarningOutlined } from '@/utils/optimizedIcons';
import { ModalSize } from '@/types/modal';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Medium} remove-from-cluster-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

export const DangerIcon = styled(WarningOutlined)`
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.fontSize.XL}px;
`;

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``;

export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const MachineNameText = styled(Text).attrs({
  variant: 'caption',
  weight: 'semibold',
})``;

export const ClusterTag = styled(RediaccTag).attrs({
  variant: 'primary',
  size: 'sm',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const MutedText = styled(Text).attrs({
  variant: 'caption',
  color: 'muted',
})``;
