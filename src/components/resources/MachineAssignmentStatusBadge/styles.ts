import styled from 'styled-components'
import { StatusBadge, StatusTag } from '@/styles/primitives'

export const AssignmentBadge = styled(StatusBadge)`
  text-transform: none;
`

export const AssignmentTag = styled(StatusTag)`
  && {
    text-transform: none;
  }
`

export const IconWrapper = styled.span`
  display: inline-flex;
  align-items: center;

  .anticon {
    font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
  }
`

export const TooltipText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`
