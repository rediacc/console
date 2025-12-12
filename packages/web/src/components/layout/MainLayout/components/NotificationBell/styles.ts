import styled from 'styled-components';
import { FlexBetween, InlineStack } from '@/components/common/styled';
import { RediaccButton, RediaccText } from '@/components/ui';
import { media } from '@/styles/mixins';
import { FlexRow } from '@/styles/primitives';

export const NotificationDropdown = styled.div`
  background-color: var(--color-bg-primary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.MD};
  max-height: ${({ theme }) => theme.dimensions.DROPDOWN_MAX_HEIGHT}px;
  min-width: ${({ theme }) => theme.dimensions.DROPDOWN_WIDTH_LG}px;
  border: 1px solid var(--color-border-secondary);

  ${media.tablet`
    min-width: 0;
    width: calc(100vw - ${({ theme }) => theme.spacing.XL}px);
    max-width: ${({ theme }) => theme.dimensions.DROPDOWN_WIDTH_LG}px;
    margin: 0 ${({ theme }) => theme.spacing.MD}px;
  `}
`;

export const NotificationHeader = styled(FlexBetween)`
  padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
  border-bottom: 1px solid var(--color-border-secondary);
  background-color: var(--color-bg-secondary);
`;

export const NotificationListWrapper = styled.div`
  max-height: ${({ theme }) => theme.dimensions.LIST_MAX_HEIGHT}px;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: ${({ theme }) => theme.borderRadius.MD}px;
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

const NOTIFICATION_TYPE_COLOR_MAP: Record<
  'success' | 'error' | 'warning' | 'info',
  keyof import('@/styles/styledTheme').StyledTheme['colors']
> = {
  success: 'success',
  error: 'error',
  warning: 'warning',
  info: 'info',
};

export const NotificationIconWrapper = styled.div<{
  $type: 'success' | 'error' | 'warning' | 'info';
}>`
  display: inline-flex;
  align-items: center;
  justify-content: center;

  .anticon {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    color: ${({ theme, $type }) => {
      const colorKey = NOTIFICATION_TYPE_COLOR_MAP[$type] ?? 'textPrimary';
      return theme.colors[colorKey];
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

export const NotificationMessageWrapper = styled.div`
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  word-break: break-word;
`;

export const EmptyWrapper = styled.div`
  padding: ${({ theme }) => `${theme.spacing.XXL}px 0`};
`;

export const BellButton = styled(RediaccButton)`
  border-radius: 50%;
  width: ${({ theme }) => theme.spacing.XXL}px;
  height: ${({ theme }) => theme.spacing.XXL}px;

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
    font-size: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const NotificationActionButton = styled(RediaccButton)`
  && {
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`;
