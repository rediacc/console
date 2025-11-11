import styled from 'styled-components'
import { Row, Space, Divider, Button, Card, Typography } from 'antd'
import { PageContainer } from '@/styles/primitives'

const { Text, Title } = Typography

export const PageWrapper = PageContainer

export const ControlsRow = styled(Row)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

export const ViewToggle = styled(Space)`
  width: 100%;
  justify-content: flex-end;
`

export const LoadingState = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing['8']}px 0;
`

export const LoadingMessage = styled(Text)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const EmptyCard = styled(Card).attrs({ className: 'page-card' })``

export const EmptyStack = styled(Space).attrs({ direction: 'vertical', align: 'center', size: 'middle' })`
  text-align: center;
`

export const HintText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const PrimaryButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing['8']}px;
  min-height: ${({ theme }) => theme.spacing['6']}px;
  background-color: ${({ theme }) => theme.colors.primary};
  border-color: ${({ theme }) => theme.colors.primary};
  color: ${({ theme }) => theme.colors.bgPrimary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};

  &:hover,
  &:focus {
    background-color: ${({ theme }) => theme.colors.primaryHover};
    border-color: ${({ theme }) => theme.colors.primaryHover};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const SecondaryButton = styled(Button)`
  min-width: ${({ theme }) => theme.spacing['8']}px;
  min-height: ${({ theme }) => theme.spacing['6']}px;
  background: transparent;
  border-color: ${({ theme }) => theme.colors.primary};
  color: ${({ theme }) => theme.colors.primary};

  &:hover,
  &:focus {
    background-color: ${({ theme }) => theme.colors.primaryBg};
    color: ${({ theme }) => theme.colors.primary};
  }
`

export const CategorySection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing['6']}px;
`

export const CategoryHeader = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const CategoryTitle = styled(Title)`
  && {
    margin: 0;
  }
`

export const CategoryDescription = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const CategoryDivider = styled(Divider)`
  margin-top: ${({ theme }) => theme.spacing.XL}px !important;
`
