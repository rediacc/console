import styled from 'styled-components';
import { BaseModal, BaseTable, FlexRow, ModalTitleRow } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag, RediaccText as Text } from '@/components/ui';
import { InfoCircleOutlined } from '@/utils/optimizedIcons';
import { ModalSize } from '@/types/modal';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} view-assignment-status-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

export const InfoIcon = styled(InfoCircleOutlined)`
  color: ${({ theme }) => theme.colors.info};
`;

export const SummaryRow = styled(FlexRow).attrs({ $gap: 'LG', $wrap: true })`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const SummaryItem = styled(InlineStack)`
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const SummaryLabel = styled(Text).attrs({
  variant: 'caption',
  color: 'muted',
})``;

export const SummaryValue = styled(Text).attrs({
  weight: 'semibold',
})``;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const MachineNameText = styled(Text).attrs({
  weight: 'semibold',
})``;

export const TeamTag = styled(RediaccTag).attrs({
  preset: 'team',
  size: 'sm',
  borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`;

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
