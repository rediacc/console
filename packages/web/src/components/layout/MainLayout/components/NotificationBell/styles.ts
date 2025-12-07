import styled from 'styled-components';
import { InlineStack, FlexBetween } from '@/components/common/styled';
import { RediaccText, RediaccButton } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';

export const NotificationDropdown = styled.div`
  background-color: var(--color-bg-primary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  max-height: 500px;
  min-width: 380px;
  border: 1px solid var(--color-border-secondary);
`;

export const NotificationHeader = styled(FlexBetween)`
  padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
  border-bottom: 1px solid var(--color-border-secondary);
  background-color: var(--color-bg-secondary);
`;

export const NotificationTitle = styled(RediaccText)`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

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
`;

export const NotificationItem = styled.div<{ $isRead: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
  cursor: pointer;
  transition: all 0.2s ease;
  background-color: ${({ $isRead }) => ($isRead ? 'transparent' : 'var(--color-bg-selected)')};
  border-bottom: 1px solid var(--color-border-secondary);
  
  &:hover {
    background-color: var(--color-bg-tertiary);
  }
  
  &:last-child {
    border-bottom: none;
  }
`;

export const NotificationIconWrapper = styled.div<{
  $type: 'success' | 'error' | 'warning' | 'info';
}>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  
  .anticon {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    color: ${({ theme, $type }) => {
      switch ($type) {
        case 'success':
          return theme.colors.success;
        case 'error':
          return theme.colors.error;
        case 'warning':
          return theme.colors.warning;
        case 'info':
          return theme.colors.info;
        default:
          return theme.colors.textPrimary;
      }
    }};
  }
`;

export const NotificationTitleRow = styled(FlexRow).attrs({
  $gap: 'XS',
  $justify: 'space-between',
})`
  width: 100%;
`;

export const NotificationTitleContent = styled(InlineStack)`
  flex: 1;
`;

export const NotificationText = styled(RediaccText)<{ $isRead: boolean }>`
  font-weight: ${({ theme, $isRead }) =>
    $isRead ? theme.fontWeight.NORMAL : theme.fontWeight.SEMIBOLD};
`;

export const NotificationTag = styled.span`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

export const NotificationCloseButton = styled(RediaccButton)`
  margin-left: auto;
  flex-shrink: 0;
`;

export const NotificationMessage = styled(RediaccText)`
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  word-break: break-word;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const NotificationTimestamp = styled(RediaccText)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const EmptyWrapper = styled.div`
  padding: ${({ theme }) => `${theme.spacing.XXL}px 0`};
`;

export const BellButton = styled(RediaccButton)`
  &:hover {
    background-color: var(--color-bg-tertiary);
    color: var(--color-primary);
  }

  &:focus,
  &:active,
  &:focus-visible {
    background-color: var(--color-bg-tertiary);
  }

  .anticon {
    font-size: 24px;
  }
`;
