import styled from 'styled-components'
import { Card, Space, Typography, Badge, Progress, List, Timeline } from 'antd'
import { Link as RouterLink } from 'react-router-dom'
import { PageContainer } from '@/styles/primitives'

const { Text } = Typography

export const PageWrapper = PageContainer

export const ContentStack = styled(Space).attrs({ direction: 'vertical', size: 'large' })`
  width: 100%;
`

export const CenteredState = styled.div`
  width: 100%;
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px 0;
`

export const DashboardCard = styled(Card)`
  width: 100%;
`

export const SectionDescription = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const ResourceTile = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  height: 100%;
  transition: ${({ theme }) => theme.transitions.DEFAULT};

  &:hover {
    box-shadow: ${({ theme }) => theme.shadows.MD};
  }
`

export const TileHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const TileMeta = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`

export const ResourceProgress = styled(Progress)`
  margin: ${({ theme }) => theme.spacing.SM}px 0;
`

export const SectionLabel = styled(Text)`
  && {
    display: block;
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    letter-spacing: ${({ theme }) => theme.letterSpacing.WIDE};
  }
`

export const SectionTitle = styled(Typography.Title)`
  && {
    margin: ${({ theme }) => theme.spacing.XS}px 0 ${({ theme }) => theme.spacing.MD}px;
  }
`

export const ScrollContainer = styled.div`
  max-height: 200px;
  overflow-y: auto;
  padding-right: ${({ theme }) => theme.spacing.XS}px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-thumb {
    background-color: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`

export const HorizontalScroll = styled.div`
  width: 100%;
  overflow-x: auto;
`

export const LicenseItem = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px ${({ theme }) => theme.spacing.MD}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  width: 100%;
`

export const LicenseHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const FlexBetween = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const InlineStack = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const StatList = styled(Space).attrs({ direction: 'vertical', size: 'middle' })`
  width: 100%;
`

export const StatRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
`

export const StatLabel = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const StatValue = styled(Text)<{ $variant?: 'default' | 'success' | 'warning' | 'error' }>`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    color: ${({ theme, $variant }) => {
      switch ($variant) {
        case 'success':
          return theme.colors.success;
        case 'warning':
          return theme.colors.warning;
        case 'error':
          return theme.colors.error;
        default:
          return theme.colors.textPrimary;
      }
    }};
  }
`

export const InlineLink = styled(RouterLink)`
  color: ${({ theme }) => theme.colors.primary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};

  &:hover {
    color: ${({ theme }) => theme.colors.primaryHover};
  }
`

export const QueueBadgeRow = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const QueueBadge = styled(Badge)<{ $variant?: 'error' | 'warning' | 'info' | 'muted' }>`
  .ant-scroll-number {
    background-color: ${({ theme, $variant }) => {
      switch ($variant) {
        case 'error':
          return theme.colors.error;
        case 'warning':
          return theme.colors.warning;
        case 'info':
          return theme.colors.info;
        case 'muted':
          return theme.colors.textMuted;
        default:
          return theme.colors.primary;
      }
    }};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const TimelineWrapper = styled(Timeline)`
  width: 100%;
`

const { Item: AntListItem } = List

export const BorderlessList = styled(List)`
  width: 100%;

  .ant-list-item {
    padding-left: 0;
    padding-right: 0;
  }
`

export const BorderlessListItem = styled(AntListItem)`
  padding-left: 0 !important;
  padding-right: 0 !important;
  border: none !important;
`

export const AuditMeta = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const EmptyState = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.LG}px 0;
`

export const Divider = styled.hr`
  border: none;
  height: 1px;
  width: 100%;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
  margin: ${({ theme }) => theme.spacing.MD}px 0;
`

export const SectionFooter = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  padding-top: ${({ theme }) => theme.spacing.SM}px;
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`

export const PlanCountBadge = styled(Badge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.textPrimary};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`

export const QuantityBadge = styled(Badge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.success};
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`
