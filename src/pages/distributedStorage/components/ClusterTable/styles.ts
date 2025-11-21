import styled from 'styled-components'
import { Button, Tag, Empty, Badge } from 'antd'
import {
  CloudServerOutlined,
  RightOutlined,
  TeamOutlined,
  DesktopOutlined,
} from '@/utils/optimizedIcons'

export const TableContainer = styled.div`
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};
  .cluster-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.FAST};
  }

  .cluster-row:hover {
    background: ${({ theme }) => theme.colors.bgHover};
  }
`

export const EmptyStateWrapper = styled(Empty)`
  && {
    margin-top: ${({ theme }) => theme.spacing.XXXL}px;
  }
`

export const CreateClusterButton = styled(Button)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const ClusterNameCell = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ExpandIcon = styled(RightOutlined)<{ $expanded: boolean }>`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
  color: ${({ theme }) => theme.colors.textTertiary};
  transition: transform ${({ theme }) => theme.transitions.FAST};
  transform: ${({ $expanded }) =>
    $expanded ? 'rotate(90deg)' : 'rotate(0deg)'};
`

export const ClusterIcon = styled(CloudServerOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const ClusterNameText = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const TeamTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.success};
    color: ${({ theme }) => theme.colors.success};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const VersionTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.info};
    color: ${({ theme }) => theme.colors.info};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const MachineCountBadgeWrapper = styled(Badge)<{ $hasMachines: boolean }>`
  .ant-badge-count {
    background: ${({ theme, $hasMachines }) =>
      $hasMachines ? theme.colors.success : theme.colors.bgSecondary};
    color: ${({ theme, $hasMachines }) =>
      $hasMachines ? theme.colors.textInverse : theme.colors.textSecondary};
  }
`

export const MachineCountIcon = styled(TeamOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const ManageMachinesButton = styled(Button)`
  && {
    padding: 0;
  }
`

export const MachineManageCell = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ActionButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`

export const ActionsContainer = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ExpandedRowContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`

export const ExpandedRowTitle = styled.h4`
  margin: 0 0 ${({ theme }) => theme.spacing.SM}px;
  font-size: ${({ theme }) => theme.fontSize.H5}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const MachinesTableWrapper = styled.div`
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};
`

export const MachineNameCell = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const MachineNameIcon = styled(DesktopOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const MachineNameText = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const MachineBridgeTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.secondary};
    color: ${({ theme }) => theme.colors.secondary};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const AssignedDateText = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
`
