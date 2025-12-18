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
  }

  .cluster-row:hover {
  }
`;

export const CreateClusterButton = styled(RediaccButton)`
  && {
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
  }
`;

export const MachineCountIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: TeamOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const ManageMachinesButton = styled(RediaccButton)`
  && {
    &:hover {
    }
  }
`;

export { ActionsRow as MachineManageCell };

export const ExpandedRowContainer = styled.div`
`;

export const ExpandedRowTitle = styled.h4`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
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
`;
