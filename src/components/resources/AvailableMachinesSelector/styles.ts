import styled from 'styled-components'
import { Select, Typography } from 'antd'
import { PillTag } from '@/styles/primitives'

const { Text } = Typography

export const StyledSelect = styled(Select)`
  && {
    width: 100%;

    .ant-select-selector {
      min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_SM}px;
      border-radius: ${({ theme }) => theme.borderRadius.MD}px !important;
      background-color: ${({ theme }) => theme.colors.inputBg};
      border-color: ${({ theme }) => theme.colors.inputBorder} !important;
      transition: ${({ theme }) => theme.transitions.DEFAULT};
      padding: 0 ${({ theme }) => theme.spacing.SM}px;
    }

    &.ant-select-focused .ant-select-selector {
      border-color: ${({ theme }) => theme.colors.primary} !important;
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    }
  }
`

export const OptionContent = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const MachineMeta = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`

export const MachineIcon = styled.span`
  display: inline-flex;
  align-items: center;
  color: ${({ theme }) => theme.colors.primary};
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`

export const MachineName = styled(Text)<{ $dimmed?: boolean }>`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    opacity: ${({ $dimmed }) => ($dimmed ? 0.6 : 1)};
  }
`

export const TeamTag = styled(PillTag).attrs({
  $variant: 'success',
  $size: 'SM',
  $borderless: true,
})`
  && {
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
  }
`

export const BridgeTag = styled(PillTag).attrs({
  $variant: 'bridge',
  $size: 'SM',
  $borderless: true,
})`
  && {
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
  }
`

export const StatusContainer = styled.div`
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const StatusTag = styled(PillTag).attrs({
  $size: 'SM',
})<{ $variant: 'cluster' | 'available' }>``

export const StatusIcon = styled.span`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`

export const StatusText = styled(Text)`
  && {
    color: inherit;
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`

export const SpinnerWrapper = styled.div`
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.LG}px 0;
`

export const EmptyDescription = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`
