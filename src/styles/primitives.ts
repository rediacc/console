import styled from 'styled-components'
import { Card, Button, Table, Typography } from 'antd'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const { Title } = Typography

export const PageContainer = styled.div.attrs({ className: 'page-container' })`
  width: 100%;
`

export const PageCard = styled(Card).attrs({ className: 'page-card' })``

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.PAGE_SECTION_GAP}px;
`

export const SectionHeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const ControlStack = styled.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  gap: ${({ theme }) => theme.spacing.MD}px;
  align-items: center;
`

export const InputSlot = styled.div`
  flex: 1 1 280px;
  min-width: 240px;
`

export const ActionBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  justify-content: flex-end;
`

export const ActionButton = styled(Button)`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT}px;
  min-height: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT}px;
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
    opacity: ${(props) => (props.$isLoading ? 0.65 : 1)};
    transition: ${({ theme }) => theme.transitions.DEFAULT};
  }
`

export const SectionDescription = styled(Typography.Paragraph)`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const StatGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const InlineBadge = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  padding: ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`

export const CardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const SectionDivider = styled.hr`
  border: none;
  height: 1px;
  width: 100%;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
  margin: ${({ theme }) => theme.spacing.LG}px 0;
`

export const ActionToolbar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const Pill = styled.span`
  display: inline-flex;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`
