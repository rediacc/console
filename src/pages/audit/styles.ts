import styled from 'styled-components'
import { Card, Space, Typography, Button } from 'antd'
import { PageContainer } from '@/styles/primitives'

const { Text } = Typography

export const PageWrapper = PageContainer

export const ContentStack = styled(Space).attrs({ direction: 'vertical', size: 'large' })`
  width: 100%;
`

export const FilterCard = styled(Card).attrs({ className: 'page-card' })``

export const FilterField = styled(Space).attrs({ direction: 'vertical', size: 'small' })`
  width: 100%;
`

export const FilterLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const PlaceholderLabel = styled(FilterLabel)`
  && {
    color: transparent;
  }
`

export const ActionButtonFull = styled(Button)`
  width: 100%;
  min-height: ${({ theme }) => theme.spacing['6']}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
`

export const CompactButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing['5']}px;
  min-height: ${({ theme }) => theme.spacing['5']}px;
`

export const TableCard = styled(Card).attrs({ className: 'page-card' })``

export const TableHeader = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const TableActions = styled(Space)`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  justify-content: flex-end;
`

export const NoResults = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px 0;
  color: ${({ theme }) => theme.colors.textSecondary};
`
