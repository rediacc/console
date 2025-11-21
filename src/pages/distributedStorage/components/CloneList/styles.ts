import styled from 'styled-components'
import { Badge, Button, Space, Tag } from 'antd'
import { CopyOutlined, CloudUploadOutlined } from '@ant-design/icons'

export const Container = styled.div`
  padding: ${({ theme }) =>
    `${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.LG}px`};
  background: var(--color-fill-quaternary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const Title = styled.h5`
  margin: 0;
  font-size: ${({ theme }) => theme.fontSize.H5}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ActionsRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const CreateButton = styled(Button)`
  && {
    min-width: ${({ theme }) => theme.spacing['6']}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`

export const TableWrapper = styled.div`
  border: 1px solid var(--color-border-secondary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};
`

export const ActionButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const IconActionButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    padding: 0;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    border: none;
    box-shadow: none;

    &:hover,
    &:focus {
      background: var(--color-fill-tertiary);
    }
  }
`

export const RemoteButton = styled(ActionButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
  }
`

export const DropdownButton = styled(IconActionButton)``

export const ExpandButton = styled(IconActionButton)`
  margin-right: ${({ theme }) => theme.spacing.SM}px;
`

export const NameCell = styled(Space)`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const CloneIcon = styled(CopyOutlined)`
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const CloneName = styled.span`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const VaultTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`

export const MachineCountBadgeWrapper = styled(Badge)<{ $active?: boolean }>`
  .ant-badge-count {
    background-color: ${({ $active }) =>
      $active ? 'var(--color-primary)' : 'var(--color-fill-tertiary)'};
    color: ${({ $active }) => ($active ? 'var(--color-white)' : 'var(--color-text-secondary)')};
    box-shadow: none;
    min-width: ${({ theme }) => theme.spacing.MD}px;
  }

  .anticon {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const MachineListWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
`

export const MachineListStack = styled(Space).attrs({
  direction: 'vertical',
  size: 'middle',
})`
  width: 100%;
`

export const MachineListHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const MachineCountTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  background: var(--color-fill-tertiary);
`

export const MachineTagGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const MachineTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  padding: 0 ${({ theme }) => theme.spacing.XS}px;
`

export const MachineListButton = styled(Button)`
  && {
    align-self: flex-start;
  }
`

export const MachineListActions = styled(Space)`
  width: 100%;
`

export const EmptyState = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px ${({ theme }) => theme.spacing.MD}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: center;
`

export const AssignButton = styled(Button)`
  && {
    min-width: ${({ theme }) => theme.spacing['7']}px;
  }
`

export const RemoteIcon = styled(CloudUploadOutlined)`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
`
