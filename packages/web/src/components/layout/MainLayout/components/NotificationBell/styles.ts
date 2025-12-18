import styled from 'styled-components';
import { FlexBetween, InlineStack } from '@/components/common/styled';
import { RediaccButton, RediaccText } from '@/components/ui';
import { media } from '@/styles/mixins';
import { FlexRow } from '@/styles/primitives';

export const NotificationDropdown = styled.div`
  max-height: ${({ theme }) => theme.dimensions.DROPDOWN_MAX_HEIGHT}px;
  min-width: ${({ theme }) => theme.dimensions.DROPDOWN_WIDTH_LG}px;

  ${media.tablet`
    min-width: 0;
    width: calc(100vw - ${({ theme }) => theme.spacing.XL}px);
    max-width: ${({ theme }) => theme.dimensions.DROPDOWN_WIDTH_LG}px;
  `}
`;

export const NotificationHeader = styled(FlexBetween)`
  padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
  font-weight: 600;
`;

export const NotificationListWrapper = styled.div`
  max-height: ${({ theme }) => theme.dimensions.LIST_MAX_HEIGHT}px;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: ${({ theme }) => theme.spacing.SM}px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.borderSecondary};
  }

  &::-webkit-scrollbar-thumb:hover {
    background: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const NotificationItem = styled.div<{ $isRead: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
  cursor: pointer;
`;

export const NotificationIconWrapper = styled.div<{
  $type: 'success' | 'error' | 'warning' | 'info';
}>`
  display: inline-flex;
  align-items: center;
  justify-content: center;

  .anticon {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
  }
`;

export const NotificationTitleRow = styled(FlexRow).attrs({
  $justify: 'space-between',
})`
  width: 100%;
`;

export const NotificationTitleContent = styled(InlineStack)`
  flex: 1;
`;

export const NotificationText = styled(RediaccText)<{ $isRead: boolean }>`
  font-weight: ${({ theme, $isRead }) =>
    $isRead ? theme.fontWeight.REGULAR : theme.fontWeight.SEMIBOLD};
`;

export const NotificationTag = styled.span``;

export const NotificationCloseButton = styled(RediaccButton)`
  flex-shrink: 0;
`;

export const NotificationMessageWrapper = styled.div`
  display: block;
  word-break: break-word;
`;

export const EmptyWrapper = styled.div`
  padding: ${({ theme }) => `${theme.spacing.XXL}px 0`};
`;

export const BellButton = styled(RediaccButton)`
  width: ${({ theme }) => theme.spacing.XXL}px;
  height: ${({ theme }) => theme.spacing.XXL}px;

  .anticon {
    font-size: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const NotificationActionButton = styled(RediaccButton)`
  && {
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;
