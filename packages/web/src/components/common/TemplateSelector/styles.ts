import styled from 'styled-components';
import { Row } from 'antd';
import { RediaccSearchInput as UnifiedSearchInput } from '@/components/ui/Form';
import { FlexRow } from '@/styles/primitives';
import {
  RediaccText as UnifiedText,
  RediaccCard,
  RediaccStack,
  RediaccEmpty,
} from '@/components/ui';
import { RediaccButton } from '@/components/ui/Button';
import { RediaccTag } from '@/components/ui/Tag';

export const SelectorContainer = styled.div`
  width: 100%;
`;

export const HeaderStack = styled(RediaccStack).attrs({ direction: 'vertical' })`
  && {
    width: 100%;
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const HelperRow = styled(FlexRow).attrs({
  $gap: 'SM',
  $justify: 'space-between',
  $wrap: true,
})``;

export const HelperText = styled(UnifiedText).attrs({
  variant: 'caption',
})``;

export const ClearButton = styled(RediaccButton).attrs({
  size: 'sm',
})`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
  }
`;

export const SearchInput = styled(UnifiedSearchInput)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const ResultCount = styled(UnifiedText).attrs({
  color: 'muted',
})`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    display: block;
  }
`;

export const NoResultsEmpty = styled(RediaccEmpty)`
  && {
    margin: ${({ theme }) => theme.spacing.MD}px 0;
  }
`;

export const TemplateGrid = styled(Row)`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const TemplateCard = styled(RediaccCard)<{
  $selected?: boolean;
  $variant?: 'default' | 'none';
}>`
  height: 100%;
  border-color: ${({ theme, $selected, $variant }) =>
    $selected
      ? $variant === 'none'
        ? theme.colors.success
        : theme.colors.primary
      : theme.colors.borderSecondary};
  border-width: ${({ $selected }) => ($selected ? '2px' : '1px')};
  border-style: ${({ $variant }) => ($variant === 'none' ? 'dashed' : 'solid')};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  position: relative;
  cursor: pointer;
  transition: ${({ theme }) => theme.transitions.HOVER};
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export const SelectionIndicator = styled.span<{ $variant?: 'default' | 'none' }>`
  position: absolute;
  top: ${({ theme }) => theme.spacing.SM}px;
  right: ${({ theme }) => theme.spacing.SM}px;
  color: ${({ theme, $variant }) =>
    $variant === 'none' ? theme.colors.success : theme.colors.primary};
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const CardStack = styled(RediaccStack).attrs({ direction: 'vertical' })`
  && {
    width: 100%;
  }
`;

export const TemplateIconWrapper = styled.div<{ $muted?: boolean }>`
  text-align: center;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  color: ${({ theme, $muted }) => ($muted ? theme.colors.textTertiary : theme.colors.textPrimary)};

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_LG}px;
  }
`;

export const TemplateTitle = styled(UnifiedText)`
  && {
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
  }
`;

export const TemplateDescription = styled(UnifiedText)`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    line-height: ${({ theme }) => theme.lineHeight.RELAXED};
  }
`;

export const DetailsButton = styled(RediaccButton).attrs({
  size: 'sm',
})`
  && {
    padding: 0;
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;

    .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
    }
  }
`;

export const DefaultTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    margin: 0;
  }
`;

export const LoadingText = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const ErrorState = styled.div`
  text-align: center;
  padding: ${({ theme }) => `${theme.spacing.MD}px 0`};
`;

export { LoadingState } from '@/styles/primitives';
