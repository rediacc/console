import styled from 'styled-components'
import { Card, Button, Table, Typography } from 'antd'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const { Title } = Typography

export const PageWrapper = styled.div.attrs({ className: 'page-container' })`
  width: 100%;
`

export const PageCard = styled(Card).attrs({ className: 'page-card' })``

export const HeaderSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.PAGE_SECTION_GAP}px;
`

export const HeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const TeamControls = styled.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  gap: ${({ theme }) => theme.spacing.MD}px;
  align-items: center;
`

export const TeamSelectorWrapper = styled.div`
  flex: 1 1 280px;
  min-width: 240px;
`

export const ButtonGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  justify-content: flex-end;
`

export const ActionButton = styled(Button)`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: ${DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE}px;
  min-height: ${DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE}px;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  transition: ${({ theme }) => theme.transitions.DEFAULT};

  &:not(:disabled):hover {
    transform: translateY(-1px);
    box-shadow: ${({ theme }) => theme.shadows.BUTTON_HOVER};
  }
`

export const PageTitle = styled(Title)`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`

export const BreadcrumbWrapper = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`

export const ContentSection = styled.div`
  min-height: 400px;
`

export const DataTable = styled(Table as any)<{ $isLoading?: boolean }>`
  .ant-spin-nested-loading {
    opacity: ${(props: any) => (props.$isLoading ? 0.65 : 1)};
    transition: ${(props: any) => props.theme.transitions.DEFAULT};
  }
`
