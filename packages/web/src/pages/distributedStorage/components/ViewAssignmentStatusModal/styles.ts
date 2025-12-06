import styled from 'styled-components';
import { Typography } from 'antd';
import { BaseModal, BaseTable, FlexRow, ModalTitleRow, PillTag } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';
import { InfoCircleOutlined } from '@/utils/optimizedIcons';
import { ModalSize } from '@/types/modal';

const { Text } = Typography;

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

export const SummaryLabel = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const SummaryValue = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const MachineNameText = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const TeamTag = styled(PillTag).attrs({
  $variant: 'success',
  $size: 'SM',
  $borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const ClusterTag = styled(PillTag).attrs({
  $variant: 'cluster',
  $size: 'SM',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const MutedText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;
