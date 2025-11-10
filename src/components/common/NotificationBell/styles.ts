import styled from 'styled-components'
import { Button, Typography } from 'antd'

const { Text } = Typography

export const NotificationDropdown = styled.div`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  box-shadow: ${({ theme }) => theme.shadows.MD};
  max-height: 500px;
  min-width: 380px;
`

export const NotificationHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`

export const NotificationTitle = styled(Text)`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`

export const NotificationListWrapper = styled.div`
  max-height: 400px;
  overflow-y: auto;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: transparent;
  }
  
  &::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb:hover {
    background: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const NotificationItem = styled.div<{ $isRead: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  cursor: pointer;
  transition: ${({ theme }) => theme.transitions.DEFAULT};
  background-color: ${({ theme, $isRead }) => 
    $isRead ? 'transparent' : theme.colors.primaryBg};
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  
  &:hover {
    background-color: ${({ theme }) => theme.colors.bgHover};
  }
  
  &:last-child {
    border-bottom: none;
  }
`

export const NotificationIconWrapper = styled.div<{ $type: 'success' | 'error' | 'warning' | 'info' }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  
  .anticon {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    color: ${({ theme, $type }) => {
      switch ($type) {
        case 'success': return theme.colors.success
        case 'error': return theme.colors.error
        case 'warning': return theme.colors.warning
        case 'info': return theme.colors.info
        default: return theme.colors.textPrimary
      }
    }};
  }
`

export const NotificationTitleRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const NotificationTitleContent = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  flex: 1;
`

export const NotificationText = styled(Text)<{ $isRead: boolean }>`
  font-weight: ${({ theme, $isRead }) => 
    $isRead ? theme.fontWeight.NORMAL : theme.fontWeight.SEMIBOLD};
`

export const NotificationTag = styled.span`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`

export const NotificationCloseButton = styled(Button)`
  margin-left: auto;
  flex-shrink: 0;
`

export const NotificationMessage = styled(Text)`
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  word-break: break-word;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const NotificationTimestamp = styled(Text)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const EmptyWrapper = styled.div`
  padding: ${({ theme }) => `${theme.spacing.XXL}px 0`};
`

export const BellButton = styled(Button)`
  width: 48px;
  height: 48px;
  min-width: 48px;
  min-height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  
  .anticon {
    font-size: 22px;
  }
`
