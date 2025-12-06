import styled from 'styled-components';
import { Button, Badge } from 'antd';
import { CloudServerOutlined, TeamOutlined, DesktopOutlined } from '@/utils/optimizedIcons';
import {
  TableContainer as BaseTableContainer,
  TableCellContent,
  TableCellText,
  ExpandIcon as BaseExpandIcon,
  PillTag,
  StyledIcon,
} from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';

export const TableContainer = styled(BaseTableContainer)`
  .cluster-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.FAST};
  }

  .cluster-row:hover {
    background: ${({ theme }) => theme.colors.bgHover};
  }
`;

export const CreateClusterButton = styled(Button)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const ClusterNameCell = styled(TableCellContent)``;

export const ExpandIcon = styled(BaseExpandIcon)<{ $expanded: boolean }>``;

export const ClusterIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudServerOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

export const ClusterNameText = styled(TableCellText)``;

export const TeamTag = styled(PillTag).attrs({
  $variant: 'team',
  $size: 'SM',
})``;

export const MachineCountBadgeWrapper = styled(Badge)<{ $hasMachines: boolean }>`
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

export const ManageMachinesButton = styled(Button)`
  && {
    padding: 0;
  }
`;

export const MachineManageCell = styled(InlineStack)``;

export const ExpandedRowContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`;

export const ExpandedRowTitle = styled.h4`
  margin: 0 0 ${({ theme }) => theme.spacing.SM}px;
  font-size: ${({ theme }) => theme.fontSize.H5}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const MachinesTableWrapper = styled(BaseTableContainer)``;

export const MachineNameCell = styled(TableCellContent)``;

export const MachineNameIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: DesktopOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

export const MachineNameText = styled(TableCellText)``;

export const MachineBridgeTag = styled(PillTag).attrs({
  $variant: 'bridge',
  $size: 'SM',
})``;

export const AssignedDateText = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
`;
