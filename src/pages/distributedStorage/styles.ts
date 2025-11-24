import styled from 'styled-components'
import { Typography } from 'antd'
import { PageContainer } from '@/styles/primitives'

const { Title } = Typography

export const PageWrapper = PageContainer

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


export const EmptyState = styled.div`
  padding: ${({ theme }) => theme.spacing['5']}px 0;
  text-align: center;
`
