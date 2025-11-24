import styled from 'styled-components'
import { Button, Tag, Empty, Card, Divider, Alert, Typography } from 'antd'
import { FolderOutlined } from '@/utils/optimizedIcons'

const { Title, Text } = Typography

const TAG_VARIANTS = {
  team: {
    background: 'var(--color-success)',
    color: 'var(--color-text-inverse)',
  },
  machine: {
    background: 'var(--color-primary)',
    color: 'var(--color-text-inverse)',
  },
  version: {
    background: 'var(--color-bg-tertiary)',
    color: 'var(--color-text-primary)',
  },
} as const

const STATUS_TONES = {
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  error: 'var(--color-error)',
  info: 'var(--color-info)',
  neutral: 'var(--color-border-secondary)',
} as const

export const PanelWrapper = styled.div<{ $splitView: boolean; $visible: boolean }>`
  position: ${({ $splitView }) => ($splitView ? 'relative' : 'fixed')};
  top: 0;
  right: ${({ $splitView, $visible }) => ($splitView ? 'auto' : ($visible ? 0 : '-520px'))};
  bottom: 0;
  width: ${({ $splitView }) => ($splitView ? '100%' : '520px')};
  max-width: 100vw;
  height: ${({ $splitView }) => ($splitView ? '100%' : 'auto')};
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

export const HeaderIcon = styled(FolderOutlined)`
  font-size: ${({ theme }) => theme.fontSize.XXXXL}px;
  color: var(--color-success);
`

export const PanelTitle = styled(Title)`
  && {
    margin: 0;
  }
`

export const CollapseButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
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
    background-color: ${({ $variant }) => TAG_VARIANTS[$variant].background};
    color: ${({ $variant }) => TAG_VARIANTS[$variant].color};
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
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

export const SectionCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const Section = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

type StackGap = 'XS' | 'SM' | 'MD' | 'LG' | 'XL'

export const Stack = styled.div<{ $gap?: StackGap }>`
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: ${({ theme, $gap = 'SM' }) => theme.spacing[$gap]}px;
`

export const InlineField = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const LabelText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: var(--color-text-secondary);
  }
`

export const ValueText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const MonospaceValue = styled(ValueText)`
  && {
    font-family: 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  }
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
  font-size: ${({ $size }) => ($size ? `${$size}px` : '16px')};
  color: ${({ $color }) => $color || 'var(--color-text-secondary)'};
`

export const StatusTag = styled(Tag)<{ $tone?: keyof typeof STATUS_TONES }>`
  && {
    border: none;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-weight: 500;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
    background-color: ${({ $tone = 'neutral' }) => STATUS_TONES[$tone]};
    color: ${({ $tone = 'neutral' }) => ($tone === 'neutral' ? 'var(--color-text-primary)' : 'var(--color-text-inverse)')};
  }
`

export const AlertWrapper = styled(Alert)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const VolumeDescription = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const VolumeList = styled.ul`
  margin: ${({ theme }) => `${theme.spacing.SM}px 0`};
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`

export const ServicesList = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const ServiceCard = styled(Card)<{ $state: 'active' | 'failed' | 'other' }>`
  && {
    border-left: 4px solid
      ${({ $state }) => {
        switch ($state) {
          case 'active':
            return 'var(--color-success)'
          case 'failed':
            return 'var(--color-error)'
          default:
            return 'var(--color-border-secondary)'
        }
      }};
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const ServiceHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`

export const ServiceMetaGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const ServiceMetaItem = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const ServiceMetaLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: var(--color-text-secondary);
  }
`

export const ServiceMetaValue = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`

export const DiskUsageMeta = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: var(--color-text-secondary);
  }
`

export const PathsCard = styled(SectionCard)``

export const ActivityCard = styled(SectionCard)``

export const ActivityMetrics = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`
