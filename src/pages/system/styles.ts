/**
 * System Page Styles - Ant Design Form Wrappers
 * 
 * NOTE: Most layout components have been moved to @/components/Layout
 * 
 * This file now only contains:
 * - Ant Design form component wrappers (Select, Input, Form.Item)
 * - Ant Design card/badge wrappers with specific styling
 * - Legacy exports for backward compatibility
 * 
 * For layout components, import from @/components/Layout:
 *   import { PageWrapper, SectionStack, ModalStack, etc. } from '@/components/ui'
 */

import styled from 'styled-components'
import { Card, Badge, Empty, Alert, Form, Select, Input, Space } from 'antd'
import { ActionButton as PrimitiveActionButton } from '@/styles/primitives'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const SpaceCompact = Space.Compact

export const ACTIONS_COLUMN_WIDTH = DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH

// ============================================
// ANT DESIGN CARD WRAPPERS
// ============================================

export const SettingsCard = styled(Card)`
  height: 100%;
`

export const DangerCard = styled(Card)`
  border-color: ${({ theme }) => theme.colors.error};
`

// ============================================
// ANT DESIGN BADGE WRAPPERS
// ============================================

export const PrimaryBadge = styled(Badge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.primary};
  }
`

// ============================================
// ANT DESIGN EMPTY STATE WRAPPERS
// ============================================

export const PaddedEmpty = styled(Empty)`
  padding: ${({ theme }) => theme.spacing['5']}px 0;
`

// ============================================
// ANT DESIGN FORM WRAPPERS
// ============================================

export const FullWidthSelect = styled(Select)`
  width: 100%;
  flex: 1 1 240px;
  min-width: 200px;
`

export const FullWidthInput = styled(Input)`
  width: 100%;
  flex: 1 1 240px;
  min-width: 200px;
`

export const TokenCopyRow = styled(SpaceCompact)`
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const ModalAlert = styled(Alert)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

export const FormItemSpaced = styled(Form.Item)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const FormItemNoMargin = styled(Form.Item)`
  && {
    margin-bottom: 0;
  }
`

export const FormItemActions = styled(Form.Item)`
  && {
    margin: ${({ theme }) => theme.spacing.LG}px 0 0;
  }
`

export const FormItemActionsLg = styled(Form.Item)`
  && {
    margin: ${({ theme }) => theme.spacing.XL}px 0 0;
  }
`

// ============================================
// LEGACY / PRIMITIVES
// ============================================

export const ActionButton = PrimitiveActionButton
