import { Row } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccCard, RediaccTag, RediaccText } from '@/components/ui';
import { RediaccSearchInput } from '@/components/ui/Form';
import { FlexRow } from '@/styles/primitives';

export const SelectorContainer = styled.div`
  width: 100%;
`;

export const HelperRow = styled(FlexRow).attrs({
  $justify: 'space-between',
  $wrap: true,
})``;

export const ClearButton = styled(RediaccButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const SearchInput = styled(RediaccSearchInput)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const ResultCount = styled(RediaccText).attrs({
  color: 'muted',
})`
  && {
    display: block;
  }
`;

export const TemplateGrid = styled(Row)`
`;

export const TemplateCard = styled(RediaccCard)<{
  $selected?: boolean;
  $variant?: 'default' | 'none';
}>`
  height: 100%;
  position: relative;
  cursor: pointer;
`;

export const SelectionIndicator = styled.span<{ $variant?: 'default' | 'none' }>`
  position: absolute;
  top: ${({ theme }) => theme.spacing.SM}px;
  right: ${({ theme }) => theme.spacing.SM}px;
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const TemplateIconWrapper = styled.div<{ $muted?: boolean }>`
  text-align: center;

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_LG}px;
  }
`;

// TemplateTitle removed - use <RediaccText variant="title"> directly

// TemplateDescription removed - use <RediaccText variant="description"> directly

export const DetailsButton = styled(RediaccButton)`
  && {
    display: inline-flex;
    align-items: center;

    .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
    }
  }
`;

export const DefaultTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  && {
  }
`;

export const LoadingText = styled.div`
`;

export const ErrorState = styled.div`
  text-align: center;
`;

export const SearchContainer = styled.div`
`;

export const EmptyResultsContainer = styled.div`
`;

export const TemplateDescription = styled.span`
  display: block;
`;

export { LoadingState } from '@/styles/primitives';
