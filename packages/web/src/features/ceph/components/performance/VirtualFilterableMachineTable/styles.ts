import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';
import { RediaccInput, RediaccSelect } from '@/components/ui/Form';
import { FlexColumn } from '@/styles/primitives';

export const Container = styled(FlexColumn).attrs({
  $gap: 'SM',
})`
  padding: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px 0;
`;

export const ToolbarStack = styled(FlexColumn).attrs({
  $gap: 'SM',
})`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const FilterInput = styled(RediaccInput)`
  && {
    width: min(320px, 100%);
    max-width: 100%;
  }
`;

export const AssignmentSelect = styled(RediaccSelect)`
  && {
    width: min(240px, 100%);
  }
`;

export const PageSizeSelect = styled(RediaccSelect)`
  && {
    width: min(200px, 100%);
  }
`;

export const RefreshButton = styled(RediaccButton)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  }
`;

export const StatusText = styled.div`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const OptionLabel = styled.span`
  padding-right: ${({ theme }) => theme.spacing.LG}px;
`;
