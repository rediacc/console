import styled from 'styled-components'
import { Card, Button, Typography } from 'antd'
import { PageContainer } from '@/styles/primitives'

const { Title } = Typography

export const PageWrapper = PageContainer

export const PageCard = styled(Card).attrs({ className: 'page-card' })``

export const HeaderSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const HeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const TitleGroup = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
  flex: 1 1 auto;
  min-width: 0;
`

export const HeaderTitle = styled(Title)`
  && {
    margin: 0;
  }
`

export const TeamSelectorWrapper = styled.div`
  flex: 1 1 auto;
  min-width: ${({ theme }) => theme.dimensions.CARD_WIDTH}px;
  max-width: ${({ theme }) => theme.dimensions.CARD_WIDTH_LG}px;

  > * {
    width: 100%;
  }
`

export const ActionGroup = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-shrink: 0;
`

const iconButtonBase = styled(Button)`
  min-width: ${({ theme }) => theme.spacing['6']}px;
  min-height: ${({ theme }) => theme.spacing['6']}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
`

export const PrimaryIconButton = styled(iconButtonBase)`
  background-color: ${({ theme }) => theme.colors.primary};
  border-color: ${({ theme }) => theme.colors.primary};
  color: ${({ theme }) => theme.colors.bgPrimary};

  &:hover,
  &:focus {
    background-color: ${({ theme }) => theme.colors.primaryHover};
    border-color: ${({ theme }) => theme.colors.primaryHover};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const SecondaryIconButton = styled(iconButtonBase)`
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const EmptyState = styled.div`
  padding: ${({ theme }) => theme.spacing['5']}px 0;
  text-align: center;
`
