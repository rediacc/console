import styled from 'styled-components'
import { Card, Row, Input, Button, Empty, Tag, Statistic } from 'antd'
import { Typography } from 'antd'
import {
  CopyOutlined,
  TeamOutlined,
  DesktopOutlined,
} from '@/utils/optimizedIcons'

const { Title, Text } = Typography

export const ManagerCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const HeaderRow = styled(Row)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

export const HeaderContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const TitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const TitleIcon = styled(CopyOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const TitleText = styled(Title).attrs({ level: 4 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const CloneName = styled.span`
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const MetadataText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const StatsRow = styled(Row)`
  height: 100%;
`

export const StatCard = styled(Statistic)<{ $highlight?: boolean }>`
  && {
    .ant-statistic-title {
      color: ${({ theme }) => theme.colors.textSecondary};
      margin-bottom: ${({ theme }) => theme.spacing.XS}px;
    }

    .ant-statistic-content-value {
      font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
      color: ${({ theme, $highlight }) =>
        $highlight ? theme.colors.primary : theme.colors.textPrimary};
    }
  }
`

export const StatIcon = styled(TeamOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const ToolbarRow = styled(Row)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  row-gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ActionButtonGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ToolbarButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    padding: 0;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`

export const SearchInput = styled(Input.Search)`
  && {
    width: 320px;
    max-width: 100%;
  }
`

export const WarningWrapper = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const TableContainer = styled.div`
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};
`

export const LoadingState = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.XL}px;
`

export const EmptyStateWrapper = styled(Empty)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.XL}px;
  }
`

export const EmptyActionButton = styled(Button)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const ModalStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const ModalPlaceholder = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.XL}px;
`

export const SelectedCountTag = styled(Tag)`
  && {
    align-self: flex-start;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.primary};
    color: ${({ theme }) => theme.colors.primary};
  }
`

export const ModalTitle = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ModalTitleIcon = styled(TeamOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.textSecondary};
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

export const MachineName = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const BridgeTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border-color: ${({ theme }) => theme.colors.success};
    background: ${({ theme }) => theme.colors.bgPrimary};
    color: ${({ theme }) => theme.colors.success};
  }
`
