import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag } from '@/components/ui';
import { BaseModal, ModalTitleRow } from '@/styles/primitives';
import { ModalSize } from '@/types/modal';
import { WarningOutlined } from '@/utils/optimizedIcons';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Medium} remove-from-cluster-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

export const DangerIcon = styled(WarningOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XL}px;
`;

export const MachineNameRow = styled(InlineStack)``;

export const ClusterTag = styled(RediaccTag).attrs({
  variant: 'primary',
  size: 'sm',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const StyledAlertCard = styled.div`
`;
