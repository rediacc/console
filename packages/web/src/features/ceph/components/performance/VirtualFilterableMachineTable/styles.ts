import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';
import { RediaccInput, RediaccSelect } from '@/components/ui/Form';
import { FlexColumn } from '@/styles/primitives';

export const Container = styled(FlexColumn).attrs({})`
`;

export const ToolbarStack = styled(FlexColumn).attrs({})`
`;

export const FilterInput = styled(RediaccInput)`
  && {
    width: min(${({ theme }) => theme.dimensions.CARD_WIDTH}px, 100%);
    max-width: 100%;
  }
`;

export const AssignmentSelect = styled(RediaccSelect)`
  && {
    width: min(${({ theme }) => theme.dimensions.SEARCH_INPUT_WIDTH_SM}px, 100%);
  }
`;

export const PageSizeSelect = styled(RediaccSelect)`
  && {
    width: min(${({ theme }) => theme.dimensions.FILTER_INPUT_WIDTH}px, 100%);
  }
`;

export const RefreshButton = styled(RediaccButton)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const StatusText = styled.div`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const OptionLabel = styled.span`
`;
