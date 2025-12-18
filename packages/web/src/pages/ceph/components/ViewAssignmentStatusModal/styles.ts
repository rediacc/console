import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag } from '@/components/ui';
import { BaseModal, FlexRow, ModalTitleRow } from '@/styles/primitives';
import { ModalSize } from '@/types/modal';
import { InfoCircleOutlined } from '@/utils/optimizedIcons';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} view-assignment-status-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

export const InfoIcon = styled(InfoCircleOutlined)`
`;

export const SummaryRow = styled(FlexRow).attrs({ $wrap: true })`
`;

export const SummaryItem = styled(InlineStack)`
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

export const ClusterTag = styled(RediaccTag).attrs({
  variant: 'primary',
  size: 'sm',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;
