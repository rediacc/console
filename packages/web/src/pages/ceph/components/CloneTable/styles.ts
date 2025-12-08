import { CopyOutlined, CloudUploadOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import { RediaccBadge } from '@/components/ui';
import { RediaccButton } from '@/components/ui';
import { TableWrapper, NameCell, ActionsRow } from '@/pages/ceph/styles/tableAliases';
import {
  FlexColumn,
  TableCellText,
  StyledIcon,
  IconActionButton,
} from '@/styles/primitives';

export const Container = styled(FlexColumn).attrs({ $gap: 'MD' })`
  padding: ${({ theme }) =>
    `${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.LG}px`};
  background: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`;

export const Title = styled.h5`
  margin: 0;
  font-size: ${({ theme }) => theme.fontSize.H5}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export { ActionsRow, TableWrapper, NameCell };

export const ExpandButton = styled(IconActionButton)`
  margin-right: ${({ theme }) => theme.spacing.SM}px;
`;

export const CloneIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CopyOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const CloneName = styled(TableCellText)`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

// VaultTag removed - use <RediaccTag variant="neutral" compact> directly

export const MachineCountBadgeWrapper = styled(RediaccBadge)<{ $active?: boolean }>`
  .ant-badge-count {
    background-color: ${({ $active, theme }) =>
      $active ? theme.colors.primary : theme.colors.bgHover};
    color: ${({ $active, theme }) => ($active ? '#ffffff' : theme.colors.textSecondary)};
    box-shadow: none;
    min-width: ${({ theme }) => theme.spacing.MD}px;
  }

  .anticon {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const MachineListWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export { ActionsRow as MachineListHeader };

// MachineCountTag removed - use <RediaccTag variant="neutral" compact> directly

export const MachineTagGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

// MachineTag removed - use <RediaccTag preset="machine" compact> directly

export const MachineListButton = styled(RediaccButton)`
  && {
    align-self: flex-start;
  }
`;

export const EmptyState = styled(FlexColumn).attrs({
  $gap: 'MD',
  $align: 'center',
})`
  padding: ${({ theme }) => `${theme.spacing.LG}px ${theme.spacing.MD}px`};
`;

export const AssignButton = styled(RediaccButton)`
  && {
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
  }
`;

export const RemoteIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudUploadOutlined,
  $size: theme.fontSize.BASE,
}))``;
