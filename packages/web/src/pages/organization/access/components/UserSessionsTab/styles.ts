import styled from 'styled-components';
import { CardTitle, RediaccButton, RediaccCard, RediaccInput, RediaccTag } from '@/components/ui';
import { FlexColumn } from '@/styles/primitives';

export const TabContainer = styled(FlexColumn).attrs({})``;

export const StyledCard = styled(RediaccCard)`
`;

export const StatCard = styled(StyledCard)`
  min-height: 100%;
`;

export const StatTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const StatSuffix = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const TableCard = styled(StyledCard)``;

export const CardTitleText = CardTitle;

export const RefreshButton = styled(RediaccButton)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: ${({ theme }) => theme.spacing.XXL}px;
    min-height: ${({ theme }) => theme.spacing.XXL}px;
    font-size: ${({ theme }) => theme.fontSize.MD}px;
  }
`;

export const SearchInput = styled(RediaccInput)`
  && {
    width: min(${({ theme }) => theme.dimensions.CARD_WIDTH}px, 100%);
    max-width: 100%;
  }
`;

export const SessionTag = styled(RediaccTag).attrs({
  size: 'sm',
})`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const CellText = styled.span<{ $muted?: boolean }>`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const TableCardTitle = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;
