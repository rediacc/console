import styled from 'styled-components'
import { Card, Space, Select, DatePicker, Input, Typography, Checkbox, Badge } from 'antd'
import { PageContainer } from '@/styles/primitives'

const { Text } = Typography
const { RangePicker } = DatePicker

export const PageWrapper = PageContainer

export const FiltersCard = styled(Card)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.SM}px ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`

export const FiltersGrid = styled(Space).attrs({ size: 8, wrap: true })`
  width: 100%;
`

export const FilterSelect = styled(Select)<{ $minWidth?: number }>`
  min-width: ${({ $minWidth }) => ($minWidth ? `${$minWidth}px` : '150px')};
`

export const FilterRangePicker = styled(RangePicker)`
  min-width: 220px;
`

export const FilterInput = styled(Input)`
  min-width: 200px;
`

export const FilterCheckbox = styled(Checkbox)`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`

export const StatsBar = styled(Space).attrs({ size: 12 })`
  align-items: center;
  flex-wrap: wrap;
`

export const StatItem = styled(Space).attrs({ size: 4 })`
  align-items: center;
`

export const StatLabel = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const StatValue = styled(Text)<{ $color?: string }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ $color, theme }) => $color || theme.colors.textPrimary};
  }
`

export const StatDivider = styled.span`
  display: inline-block;
  width: 1px;
  height: 16px;
  background-color: ${({ theme }) => theme.colors.borderSecondary};
`

export const StatIcon = styled.span<{ $color?: string }>`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ $color, theme }) => $color || theme.colors.textSecondary};
`


export const TabLabel = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const TabCount = styled(Badge)<{ $color?: string }>`
  .ant-scroll-number {
    background-color: ${({ $color, theme }) => $color || theme.colors.primary};
  }
`
