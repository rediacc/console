import styled from 'styled-components'
import { Button, Card, Tag, Badge, Empty } from 'antd'
import { DesktopOutlined } from '@/utils/optimizedIcons'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const TAG_VARIANTS = {
  team: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  bridge: {
    background: 'var(--color-primary)',
    color: 'var(--color-text-inverse)',
  },
  region: {
    background: 'var(--color-info)',
    color: 'var(--color-text-inverse)',
  },
  repo: {
    background: 'var(--color-secondary)',
    color: 'var(--color-text-inverse)',
  },
  status: {
    background: 'var(--color-warning)',
    color: 'var(--color-text-inverse)',
  },
  grand: {
    background: 'var(--color-secondary)',
    color: 'var(--color-text-inverse)',
  },
} as const

export type TagVariant = keyof typeof TAG_VARIANTS

export const MachineTableWrapper = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: ${({ theme }) => theme.spacing.MD}px;

  .machine-table-row {
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .machine-table-row:hover {
    background-color: var(--color-bg-hover);
  }

  .machine-table-row--selected td {
    background-color: var(--color-bg-selected);
  }
`

export const TableContainer = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`

export const BulkActionsBar = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.SM}px ${({ theme }) => theme.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const BulkActionsSummary = styled.span`
  font-weight: 600;
  color: var(--color-text-primary);
`

export const ViewToggleContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const ViewToggleButton = styled(Button)`
  && {
    min-width: 42px;
    height: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`

export const ViewToggleDivider = styled.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({ theme }) => theme.spacing.SM}px;
`

export const EmptyState = styled(Empty).attrs({
  image: Empty.PRESENTED_IMAGE_SIMPLE,
})`
  margin-top: ${({ theme }) => theme.spacing.XL}px;
`

export const GroupedCardStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XL}px;
`

export const GroupCardContainer = styled(Card)<{ $isAlternate: boolean }>`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 2px solid ${({ $isAlternate }) => ($isAlternate ? 'var(--color-border-primary)' : 'var(--color-border-secondary)')};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    background-color: ${({ $isAlternate }) => ($isAlternate ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)')};
  }

  .ant-card-head {
    background-color: ${({ $isAlternate }) => ($isAlternate ? 'var(--color-bg-hover)' : 'var(--color-bg-primary)')};
    border-bottom: 2px solid ${({ $isAlternate }) => ($isAlternate ? 'var(--color-border-primary)' : 'var(--color-border-secondary)')};
  }

  .ant-card-body {
    padding: 0;
    background-color: ${({ $isAlternate }) => ($isAlternate ? 'var(--color-bg-hover)' : 'var(--color-bg-primary)')};
  }
`

export const GroupCardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => theme.spacing.XS}px 0;
`

export const GroupCardIndicator = styled.div<{ $color?: string }>`
  width: 4px;
  height: ${DESIGN_TOKENS.DIMENSIONS.ICON_XL}px;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  background-color: ${({ $color }) => $color || 'var(--color-text-secondary)'};
`

export const GroupCardTitle = styled.span`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
`

export const GroupCardCount = styled.span`
  font-size: 14px;
  color: var(--color-text-secondary);
`

export const GroupCardRow = styled.div<{ $isStriped: boolean }>`
  padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.LG}px`};
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--color-border-secondary);
  background-color: ${({ $isStriped }) => ($isStriped ? 'var(--color-bg-tertiary)' : 'transparent')};
  cursor: pointer;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: var(--color-bg-hover);
  }

  &:last-child {
    border-bottom: none;
  }
`

export const GroupRowContent = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const MachineNameIcon = styled(DesktopOutlined)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`

export const GroupRowIcon = styled(MachineNameIcon)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_LG}px;
`

export const GroupRowInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const GroupRowName = styled.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
`

export const GroupRowActionButton = styled(Button)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    height: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const StatusIcon = styled.span<{ $status: 'online' | 'offline' | 'unknown' }>`
  font-size: 18px;
  color: ${({ $status }) => {
    switch ($status) {
      case 'online':
        return 'var(--color-success)'
      case 'offline':
        return 'var(--color-text-tertiary)'
      default:
        return 'var(--color-text-quaternary)'
    }
  }};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`

export const StyledTag = styled(Tag)<{ $variant: TagVariant }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    line-height: 24px;
    background-color: ${({ $variant }) => TAG_VARIANTS[$variant].background};
    color: ${({ $variant }) => TAG_VARIANTS[$variant].color};
  }
`

export const GroupHeaderTag = styled(StyledTag)`
  && {
    font-size: 16px;
    padding: 4px ${({ theme }) => theme.spacing.MD}px;
  }
`

export const StyledBadge = styled(Badge)<{ $isPositive: boolean }>`
  && .ant-badge-count {
    background-color: ${({ $isPositive }) => ($isPositive ? 'var(--color-success)' : 'var(--color-border-secondary)')};
    color: ${({ $isPositive }) => ($isPositive ? 'var(--color-text-inverse)' : 'var(--color-text-secondary)')};
  }
`
