import styled from 'styled-components';
import { RediaccText } from '@/components/ui';
import { RediaccTag } from '@/components/ui/Tag';

export const TooltipContent = styled.div`
  display: flex;
  flex-direction: column;
  min-width: ${({ theme }) => theme.dimensions.SEARCH_INPUT_WIDTH_SM}px;
`;

export const TooltipContentSection = styled.div`
  width: 100%;
`;

export const SeverityPill = styled(RediaccTag)<{ $color?: string }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
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
  }
`;

export const StyledRediaccCard = styled.div`
`;

export const PriorityTooltipTitle = styled(RediaccText).attrs({
  weight: 'bold',
})`
  && {
    display: block;
  }
`;

export const AgeText = styled(RediaccText)<{ $color?: string }>`
  && {
  }
`;

export const ErrorMessageText = styled(RediaccText).attrs({
  size: 'sm',
})<{ $isLast?: boolean }>`
  && {
    display: block;
  }
`;

export const LastRetryText = styled(RediaccText).attrs({
  size: 'sm',
})`
  && {
    display: block;
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
