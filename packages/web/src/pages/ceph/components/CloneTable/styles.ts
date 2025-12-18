import { CloudUploadOutlined, CopyOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import { RediaccBadge, RediaccButton } from '@/components/ui';
import { TableCellText } from '@/components/ui/Table';
import { ActionsRow, NameCell, TableWrapper } from '@/pages/ceph/styles/tableAliases';
import { FlexColumn, IconActionButton, StyledIcon } from '@/styles/primitives';

export const Container = styled(FlexColumn).attrs({})`
`;

export const Title = styled.h5`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export { ActionsRow, TableWrapper, NameCell };

export const ExpandButton = styled(IconActionButton)`
`;

export const CloneIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CopyOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const CloneName = styled(TableCellText)`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

// VaultTag removed - use <RediaccTag variant="neutral" compact> directly

export const MachineCountBadgeWrapper = styled(RediaccBadge)<{ $active?: boolean }>`
  .ant-badge-count {
    min-width: ${({ theme }) => theme.spacing.MD}px;
  }

  .anticon {
  }
`;

export const MachineListWrapper = styled.div`
`;

export { ActionsRow as MachineListHeader };

// MachineCountTag removed - use <RediaccTag variant="neutral" compact> directly

export const MachineTagGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
`;

// MachineTag removed - use <RediaccTag preset="machine" compact> directly

export const MachineListButton = styled(RediaccButton)`
  && {
    align-self: flex-start;
  }
`;

export const EmptyState = styled(FlexColumn).attrs({
  $align: 'center',
})`
`;

export const AssignButton = styled(RediaccButton)`
  && {
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
  }
`;

export const RemoteIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudUploadOutlined,
  $size: theme.fontSize.MD,
}))``;
