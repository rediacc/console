/**
 * Form layout components
 * 
 * Components for form layouts:
 * - InlineFormRow: Horizontal form layout with wrapping
 */

import styled from 'styled-components'

/**
 * InlineFormRow - Horizontal form layout with wrapping
 */
export const InlineFormRow = styled.div`
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: flex-start;
`
