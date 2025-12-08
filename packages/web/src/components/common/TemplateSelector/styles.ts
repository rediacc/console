import { Row } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccCard, RediaccTag, RediaccText } from '@/components/ui';
import { RediaccSearchInput } from '@/components/ui/Form';
import { FlexRow } from '@/styles/primitives';

export const SelectorContainer = styled.div`
  width: 100%;
`;

export const HelperRow = styled(FlexRow).attrs({
  $gap: 'SM',
  $justify: 'space-between',
  $wrap: true,
})``;

export const ClearButton = styled(RediaccButton).attrs({
  size: 'sm',
})`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
  }
`;

export const SearchInput = styled(RediaccSearchInput)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const ResultCount = styled(RediaccText).attrs({
  color: 'muted',
})`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    display: block;
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

export const TemplateIconWrapper = styled.div<{ $muted?: boolean }>`
  text-align: center;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  color: ${({ theme, $muted }) => ($muted ? theme.colors.textTertiary : theme.colors.textPrimary)};

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_LG}px;
  }
`;

// TemplateTitle removed - use <RediaccText variant="title"> directly

// TemplateDescription removed - use <RediaccText variant="description"> directly

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
