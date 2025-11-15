import styled from 'styled-components'
import { Card, Button, Table, Typography, Modal, Tag } from 'antd'
import type { StyledTheme } from '@/styles/styledTheme'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const { Title } = Typography

export type StatusVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'processing'

const resolveStatusTokens = (variant: StatusVariant = 'info', theme: StyledTheme) => {
  switch (variant) {
    case 'success':
      return {
        bg: theme.colors.bgSuccess,
        color: theme.colors.success,
        border: theme.colors.success,
      }
    case 'warning':
      return {
        bg: theme.colors.bgWarning,
        color: theme.colors.warning,
        border: theme.colors.warning,
      }
    case 'error':
      return {
        bg: theme.colors.bgError,
        color: theme.colors.error,
        border: theme.colors.error,
      }
    case 'processing':
      return {
        bg: theme.colors.primaryBg,
        color: theme.colors.primary,
        border: theme.colors.primary,
      }
    case 'neutral':
      return {
        bg: theme.colors.bgSecondary,
        color: theme.colors.textSecondary,
        border: theme.colors.borderSecondary,
      }
    case 'info':
    default:
      return {
        bg: theme.colors.bgInfo,
        color: theme.colors.info,
        border: theme.colors.info,
      }
  }
}

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

export const StatusBadge = styled.span<{ $variant?: StatusVariant }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  padding: ${({ theme }) => `${theme.spacing.XS}px ${theme.spacing.SM}px`};
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).bg};
  color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
  border: 1px solid ${({ theme, $variant }) => resolveStatusTokens($variant, theme).border};
  line-height: 1;
  text-transform: none;
`

export const StatusTag = styled(Tag)<{ $variant?: StatusVariant }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).border};
    color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
    background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).bg};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const StatusDot = styled.span<{ $variant?: StatusVariant }>`
  width: 8px;
  height: 8px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
  flex-shrink: 0;
`

export const IconButton = styled(Button)`
  width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  border-radius: ${({ theme }) => theme.borderRadius.FULL}px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: ${({ theme }) => theme.transitions.BUTTON};

  &:not(:disabled):hover {
    box-shadow: ${({ theme }) => theme.shadows.BUTTON_HOVER};
    transform: translateY(-1px);
  }

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  }
`

export const InlineStack = styled.div<{ $align?: 'flex-start' | 'center' | 'flex-end' }>`
  display: inline-flex;
  align-items: ${({ $align }) => $align || 'center'};
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`

export const ScrollArea = styled.div<{ $maxHeight?: number | string }>`
  max-height: ${({ $maxHeight }) => {
    if (!$maxHeight) return 'none'
    return typeof $maxHeight === 'number' ? `${$maxHeight}px` : $maxHeight
  }};
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const PanelCard = styled.div`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
  padding: ${({ theme }) => theme.spacing.LG}px;
`

export const SectionTitleRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`

export const KeyValueGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
  margin: 0;

  dt {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
    margin: 0;
  }

  dd {
    margin: 0;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const BaseModal = styled(Modal)`
  .ant-modal-content {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    border-radius: ${({ theme }) => theme.borderRadius.XL}px;
    box-shadow: ${({ theme }) => theme.shadows.MODAL};
  }

  .ant-modal-header {
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-modal-title {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }

  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.LG}px;
  }

  .ant-modal-footer {
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const ModalHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const ModalTitle = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ModalSubtitle = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`

export const ModalBody = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const ModalFooter = styled.div`
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ModalSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ModalSectionTitle = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ModalSectionDescription = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`

export const FormSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
`

export const FormFieldRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.MD}px;
  align-items: flex-start;
`

export const FieldLabel = styled.label`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`

export const FieldDescription = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`

export const DetailList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const DetailListItem = styled.li`
  display: flex;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};

  span {
    &:first-child {
      color: ${({ theme }) => theme.colors.textSecondary};
    }
  }
`

export const InfoBanner = styled.div<{ $variant?: StatusVariant }>`
  display: flex;
  gap: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  background-color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).bg};
  border: 1px solid ${({ theme, $variant }) => resolveStatusTokens($variant, theme).border};
  color: ${({ theme, $variant }) => resolveStatusTokens($variant, theme).color};
`

export const BaseTable = styled(Table as any)<{ $isInteractive?: boolean }>`
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;

  .ant-table {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-table-thead > tr > th {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    color: ${({ theme }) => theme.colors.textSecondary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }

  ${(props) =>
    props.$isInteractive
      ? `
    .ant-table-tbody > tr {
      transition: ${props.theme.transitions.DEFAULT};
    }

    .ant-table-tbody > tr:hover td {
      background-color: ${props.theme.colors.bgHover};
    }
  `
      : ''}
`

export const ModalGrid = styled.div<{ $sidebarWidth?: number }>`
  display: flex;
  gap: ${({ theme }) => theme.spacing.LG}px;
  align-items: flex-start;
  flex-wrap: wrap;

  > *:first-child {
    flex: 1 1 60%;
    min-width: min(520px, 100%);
  }

  > *:last-child {
    flex: 0 0 ${({ $sidebarWidth, theme }) =>
      $sidebarWidth ? `${$sidebarWidth}px` : `${theme.spacing.XL * 4}px`};
    min-width: 280px;
  }
`

export const ScrollablePanel = styled.div<{ $maxHeight?: number }>`
  max-height: ${({ $maxHeight }) => ($maxHeight ? `${$maxHeight}px` : '60vh')};
  overflow-y: auto;
  padding-right: ${({ theme }) => theme.spacing.SM}px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-thumb {
    background-color: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`
