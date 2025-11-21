import styled from 'styled-components'
import { Button, Tag, Space } from 'antd'
import { CameraOutlined } from '@ant-design/icons'

export const Container = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: var(--color-fill-quaternary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const Title = styled.h4`
  margin: 0;
  font-size: ${({ theme }) => theme.fontSize.H4}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ActionsRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const CreateButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-width: ${({ theme }) => theme.spacing['6']}px;
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
    justify-content: center;
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    padding: 0;
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    background: transparent;
    box-shadow: none;
    color: ${({ theme }) => theme.colors.textPrimary};
    transition: background ${({ theme }) => theme.transitions.FAST};
  }

  &&:hover,
  &&:focus {
    background: var(--color-fill-tertiary);
  }
`

export const ExpandButton = styled(ActionButton)`
  margin-right: ${({ theme }) => theme.spacing.SM}px;
`

export const NameCell = styled(Space)`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const NameIcon = styled(CameraOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.primary};
`

export const NameText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const VaultTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`

export const GuidText = styled.span`
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`
