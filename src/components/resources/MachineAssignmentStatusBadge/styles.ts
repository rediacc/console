import styled from 'styled-components'
import { Tag, Badge } from 'antd'

/**
 * Grayscale status indicators using opacity variations
 * - Solid (1.0): Available/Active states
 * - Medium (0.7): Processing/In-use states
 * - Light (0.5): Inactive states
 */

interface StyledTagProps {
  $opacity: number
}

export const StyledTag = styled(Tag)<StyledTagProps>`
  margin: 0;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  display: flex;
  align-items: center;
  gap: 4px;
  background-color: rgba(26, 26, 26, ${props => props.$opacity}) !important;
  border-color: rgba(26, 26, 26, ${props => props.$opacity * 0.8}) !important;
  color: ${props => props.$opacity >= 0.7 ? '#ffffff' : props.theme.colors.textPrimary} !important;

  .anticon {
    color: ${props => props.$opacity >= 0.7 ? '#ffffff' : props.theme.colors.textPrimary} !important;
  }

  [data-theme="dark"] & {
    background-color: rgba(200, 200, 200, ${props => props.$opacity}) !important;
    border-color: rgba(200, 200, 200, ${props => props.$opacity * 0.8}) !important;
    color: ${props => props.$opacity >= 0.7 ? '#1a1a1a' : props.theme.colors.textPrimary} !important;

    .anticon {
      color: ${props => props.$opacity >= 0.7 ? '#1a1a1a' : props.theme.colors.textPrimary} !important;
    }
  }
`

interface StyledBadgeWrapperProps {
  $opacity: number
}

export const StyledBadgeWrapper = styled.span<StyledBadgeWrapperProps>`
  .ant-badge-status-dot {
    width: 8px;
    height: 8px;
    background-color: rgba(26, 26, 26, ${props => props.$opacity}) !important;
    border: 1px solid rgba(26, 26, 26, ${props => props.$opacity * 0.5}) !important;
  }

  [data-theme="dark"] & .ant-badge-status-dot {
    background-color: rgba(200, 200, 200, ${props => props.$opacity}) !important;
    border: 1px solid rgba(200, 200, 200, ${props => props.$opacity * 0.5}) !important;
  }
`
