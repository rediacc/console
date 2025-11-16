import styled, { css } from 'styled-components'
import { Card, Input, Space, Typography, Button } from 'antd'

const { Text } = Typography

export const ContainerCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    border-color: ${({ theme }) => theme.colors.borderSecondary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const HeaderSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

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
`

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
`

export const FiltersSlot = styled.div`
  display: flex;
  align-items: center;
`

export const ActionsGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }
`

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
`

export const LoadingState = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.XXXXL}px 0;
`

export const EmptyDescriptionStack = styled(Space).attrs({
  direction: 'vertical',
  align: 'center',
  size: 'middle' as const,
})`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px;
`

export const EmptyTitle = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
  }
`

export const EmptySubtitle = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const EmptyActions = styled(Space).attrs({
  size: 'small' as const,
})`
  display: flex;
  justify-content: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

const actionButtonStyles = css`
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`

export const CreateButton = styled(Button)`
  && {
    ${actionButtonStyles};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`

export const RefreshButton = styled(Button)`
  && {
    ${actionButtonStyles};
  }
`

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

  /* Shrink the select in pagination */
  .ant-pagination-options {
    .ant-select {
      .ant-select-selector {
        height: 32px !important;
        min-height: 32px !important;
        padding: 0 32px 0 12px !important; /* Space for arrow on right, text on left */
      }
      
      .ant-select-selection-item {
        line-height: 30px !important;
        padding-right: 0 !important;
      }
      
      .ant-select-arrow {
        top: 50% !important;
        transform: translateY(-50%) !important;
        right: 6px !important;
      }
    }
  }
`
