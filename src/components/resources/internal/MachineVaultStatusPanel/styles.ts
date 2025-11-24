import styled from 'styled-components'
import { Typography, Button, Tag, Badge, Card, Empty, Divider, List } from 'antd'
import { CloudServerOutlined } from '@/utils/optimizedIcons'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const { Title, Text } = Typography

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
  queue: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  version: {
    background: 'var(--color-bg-tertiary)',
    color: 'var(--color-text-primary)',
  },
} as const

export const PanelWrapper = styled.div<{ $splitView: boolean; $visible: boolean }>`
  position: ${({ $splitView }) => ($splitView ? 'relative' : 'fixed')};
  top: 0;
  right: ${({ $splitView, $visible }) => ($splitView ? 'auto' : ($visible ? 0 : '-520px'))};
  bottom: 0;
  width: ${({ $splitView }) => ($splitView ? '100%' : '520px')};
  max-width: 100vw;
  background-color: var(--color-bg-primary);
  box-shadow: ${({ $splitView }) => ($splitView ? 'none' : '-2px 0 8px rgba(0, 0, 0, 0.15)')};
  transition: right 0.3s ease-in-out;
  overflow-y: auto;
  overflow-x: hidden;
  z-index: ${({ $splitView, theme }) => ($splitView ? 'auto' : theme.zIndex.MODAL)};
`

export const StickyHeader = styled.div`
  position: sticky;
  top: 0;
  z-index: 2;
  background-color: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-secondary);
  padding: ${({ theme }) => `${theme.spacing['1.5']}px ${theme.spacing.PAGE_CARD_PADDING}px`};
`

export const HeaderRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const HeaderTitleGroup = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const HeaderIcon = styled(CloudServerOutlined)`
  font-size: ${DESIGN_TOKENS.DIMENSIONS.ICON_XL}px;
  color: var(--color-primary);
`

export const MachineName = styled(Title)`
  && {
    margin: 0;
  }
`

export const CollapseButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT}px;
    height: ${DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border-color: var(--color-border-secondary);
    color: var(--color-text-secondary);
  }
`

export const TagRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const StyledTag = styled(Tag)<{ $variant: keyof typeof TAG_VARIANTS }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    background-color: ${({ $variant }) => TAG_VARIANTS[$variant].background};
    color: ${({ $variant }) => TAG_VARIANTS[$variant].color};
  }
`

export const QueueBadge = styled(Badge)`
  && .ant-badge-count {
    background-color: var(--color-success);
    color: var(--color-text-inverse);
  }
`

export const TimestampWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const Timestamp = styled(Text)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
    color: var(--color-text-secondary);
  }
`

export const ContentWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.PAGE_CARD_PADDING}px;
`

export const EmptyState = styled(Empty)`
  margin-top: ${({ theme }) => theme.spacing.XXXL}px;
`

export const SectionDivider = styled(Divider).attrs({
  orientation: 'left',
})`
  margin: ${({ theme }) => `${theme.spacing.XL}px 0`};
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const SectionTitle = styled(Title)`
  && {
    margin: 0;
  }
`

export const IconWrapper = styled.span<{ $color?: string; $size?: number }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ $size }) => $size || DESIGN_TOKENS.DIMENSIONS.ICON_MD}px;
  color: ${({ $color }) => $color || 'var(--color-text-secondary)'};
`

export const SectionBlock = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XL}px;
`

export const InfoCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const FullWidthStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  width: 100%;
`

export const InlineField = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const FieldLabel = styled(Text)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
    color: var(--color-text-secondary);
  }
`

export const FieldValue = styled(Text)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.SM}px;
    color: var(--color-text-primary);
  }
`

export const FieldValueStrong = styled(FieldValue)`
  && {
    font-weight: 600;
  }
`

export const FieldValueMonospace = styled(FieldValue)`
  && {
    font-family: 'SFMono-Regular', Monaco, Consolas, 'Liberation Mono', monospace;
  }
`

export const SecondaryText = styled(Text)`
  && {
    font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
    color: var(--color-text-secondary);
  }
`

export const MetricCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const CardHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`

export const CardTitle = styled(Title)`
  && {
    margin: 0;
    font-size: ${DESIGN_TOKENS.FONT_SIZE.BASE}px;
  }
`

export const CardTagGroup = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

const STATUS_TONES = {
  success: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  info: {
    background: 'var(--color-info)',
    color: 'var(--color-text-inverse)',
  },
  warning: {
    background: 'var(--color-warning)',
    color: 'var(--color-text-inverse)',
  },
  default: {
    background: 'var(--color-bg-tertiary)',
    color: 'var(--color-text-primary)',
  },
} as const

export const StatusTag = styled(Tag)<{ $tone?: keyof typeof STATUS_TONES }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    font-weight: 500;
    background-color: ${({ $tone = 'default' }) => STATUS_TONES[$tone].background};
    color: ${({ $tone = 'default' }) => STATUS_TONES[$tone].color};
  }
`

export const AddressTag = styled(Tag)`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    background-color: var(--color-info);
    color: var(--color-text-inverse);
  }
`

export const StyledList = styled(List)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const ListCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const CardBodyStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const KeyValueRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const IndentedBlock = styled.div`
  margin-left: ${({ theme }) => theme.spacing.MD}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const PartitionRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
  font-size: ${DESIGN_TOKENS.FONT_SIZE.CAPTION}px;
  color: var(--color-text-secondary);
`
