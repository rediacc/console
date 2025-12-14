import styled from 'styled-components';
import { RediaccBadge, RediaccButton } from '@/components/ui';
import { TableWrapper as UITableWrapper } from '@/components/ui/Table';
import {
  ActionsRow,
  ExpandIcon,
  NameCell,
  NameText,
  TableWrapper,
} from '@/pages/ceph/styles/tableAliases';
import { StyledIcon } from '@/styles/primitives';
import { CloudServerOutlined, DesktopOutlined, TeamOutlined } from '@/utils/optimizedIcons';

export const TableContainer = styled(UITableWrapper).attrs({ $variant: 'default' })`
  .cluster-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.FAST};
  }

  .cluster-row:hover {
    background: ${({ theme }) => theme.colors.bgHover};
  }
`;

export const CreateClusterButton = styled(RediaccButton)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export { NameCell as ClusterNameCell, ExpandIcon, NameText as ClusterNameText };

export const ClusterIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudServerOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

// TeamTag removed - use <RediaccTag preset="team" compact borderless> directly

export const MachineCountBadgeWrapper = styled(RediaccBadge)<{ $hasMachines: boolean }>`
  .ant-badge-count {
    background: ${({ theme, $hasMachines }) =>
      $hasMachines ? theme.colors.success : theme.colors.bgSecondary};
    color: ${({ theme, $hasMachines }) =>
      $hasMachines ? theme.colors.textInverse : theme.colors.textSecondary};
  }
`;

export const MachineCountIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: TeamOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const ManageMachinesButton = styled(RediaccButton)`
  && {
    padding: 0;
    background: transparent;
    border: none;
    color: ${({ theme }) => theme.colors.primary};

    &:hover {
      color: ${({ theme }) => theme.colors.primaryHover};
      background: transparent;
    }
  }
`;

export { ActionsRow as MachineManageCell };

export const ExpandedRowContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`;

export const ExpandedRowTitle = styled.h4`
  margin: 0 0 ${({ theme }) => theme.spacing.SM}px;
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export {
  TableWrapper as MachinesTableWrapper,
  NameCell as MachineNameCell,
  NameText as MachineNameText,
};

export const MachineNameIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: DesktopOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

// MachineBridgeTag removed - use <RediaccTag preset="bridge" compact borderless> directly

export const AssignedDateText = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
`;
