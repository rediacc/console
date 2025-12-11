import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag } from '@/components/ui';
import { BaseModal, BaseTable, ModalTitleRow } from '@/styles/primitives';
import { ModalSize } from '@/types/modal';
import { WarningOutlined } from '@/utils/optimizedIcons';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Medium} remove-from-cluster-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

export const DangerIcon = styled(WarningOutlined)`
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.fontSize.XL}px;
`;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const ClusterTag = styled(RediaccTag).attrs({
  variant: 'primary',
  size: 'sm',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const StyledAlertCard = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;
