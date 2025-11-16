/**
 * Modal components
 * 
 * Layout components for modal content:
 * - ModalStack: Vertical stack for modal content
 * - ModalStackLarge: Larger gap variant
 * - ModalActions: Action buttons container
 */

import styled from 'styled-components'

/**
 * ModalStack - Vertical stack for modal content
 */
export const ModalStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const ModalStackLarge = styled(ModalStack)`
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const ModalActions = styled.div`
  width: 100%;
  display: flex;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.spacing.SM}px;
`
