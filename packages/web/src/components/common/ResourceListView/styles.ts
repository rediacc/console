import styled, { css } from 'styled-components';
import { Card, Input, Space, Button } from 'antd';
import { EmptyStateTitle, EmptyStateDescription } from '@/styles/primitives';

export const ContainerCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    border-color: ${({ theme }) => theme.colors.borderSecondary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const HeaderSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const HeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
  }
`;

export const ControlGroup = styled.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
  }
`;

export const FiltersSlot = styled.div`
  display: flex;
  align-items: center;
`;

export const ActionsGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }
`;

export const SearchInput = styled(Input.Search)`
  && {
    width: 300px;
    min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }

  @media (max-width: 768px) {
    && {
      width: 100%;
    }
  }
`;

export const EmptyDescriptionStack = styled(Space).attrs({
  orientation: 'vertical',
  align: 'center',
  size: 'middle' as const,
})`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px;
`;

export { EmptyStateTitle as EmptyTitle, EmptyStateDescription as EmptySubtitle };

export const EmptyActions = styled(Space).attrs({
  size: 'small' as const,
})`
  display: flex;
  justify-content: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

const actionButtonStyles = css`
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`;

export const CreateButton = styled(Button)`
  && {
    ${actionButtonStyles};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;

export const RefreshButton = styled(Button)`
  && {
    ${actionButtonStyles};
  }
`;

export const TableWrapper = styled.div`
  /* Better scroll experience on mobile devices */
  @media (max-width: 576px) {
    -webkit-overflow-scrolling: touch;
    
    .ant-table-wrapper {
      overflow-x: auto;
    }
    
    .ant-table-pagination {
      flex-wrap: wrap;
      justify-content: center;
      gap: ${({ theme }) => theme.spacing.SM}px;
      
      .ant-pagination-total-text {
        flex-basis: 100%;
        text-align: center;
        margin-bottom: ${({ theme }) => theme.spacing.XS}px;
      }
    }
  }

`;
