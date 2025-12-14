import styled from 'styled-components';
import { RediaccText } from '@/components/ui';
import { RediaccTag } from '@/components/ui/Tag';

export const TooltipContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS / 2}px;
  min-width: ${({ theme }) => theme.dimensions.SEARCH_INPUT_WIDTH_SM}px;
`;

export const TooltipContentSection = styled.div`
  width: 100%;
`;

export const SeverityPill = styled(RediaccTag)<{ $color?: string }>`
  && {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
    ${({ $color }) => $color && `background-color: ${$color}; border-color: ${$color}; color: white;`}
  }
`;

export const TruncatedErrorText = styled(RediaccText).attrs({ size: 'sm', color: 'muted' })`
  && {
    display: inline-flex;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
`;

export const RetrySummaryTag = styled(RediaccTag)<{ $color?: string }>`
  && {
    margin: 0;
    ${({ $color }) => $color && `background-color: ${$color}; border-color: ${$color}; color: white;`}
  }
`;

export const StyledRediaccCard = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const PriorityTooltipTitle = styled(RediaccText).attrs({
  weight: 'bold',
})`
  && {
    margin: 0;
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.XS / 2}px;
  }
`;

export const AgeText = styled(RediaccText)<{ $color?: string }>`
  && {
    color: ${({ $color, theme }) => $color || theme.colors.textPrimary};
  }
`;

export const ErrorMessageText = styled(RediaccText).attrs({
  size: 'sm',
})<{ $isLast?: boolean }>`
  && {
    display: block;
    margin-bottom: ${({ theme, $isLast }) => ($isLast ? 0 : theme.spacing.XS / 2)}px;
  }
`;

export const LastRetryText = styled(RediaccText).attrs({
  size: 'sm',
})`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.XS}px;
    padding-top: ${({ theme }) => theme.spacing.XS / 2}px;
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const AdditionalMessagesText = styled(RediaccText).attrs({
  size: 'xs',
  color: 'muted',
})`
  && {
    font-style: italic;
  }
`;
