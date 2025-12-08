/**
 * System Page Styles - Ant Design Form Wrappers
 *
 * NOTE: Most layout components have been moved to @/components/Layout
 *
 * This file now only contains:
 * - Ant Design form component wrappers (Select, RediaccInput as Input, Form.Item)
 * - Ant Design card/badge wrappers with specific styling
 * - Legacy exports for backward compatibility
 *
 * For layout components, import from @/components/Layout:
 *   import { PageWrapper, SectionStack, ModalStack, etc. } from '@/components/ui'
 */

import { Form, Space } from 'antd';
import styled from 'styled-components';
import { RediaccAlert, RediaccBadge, RediaccCard } from '@/components/ui';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

const SpaceCompact = Space.Compact;

export const ACTIONS_COLUMN_WIDTH = DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH;

// ============================================
// ANT DESIGN CARD WRAPPERS
// ============================================

/**
 * @deprecated Use <RediaccCard fullHeight /> directly
 */
export const SettingsCard = styled(RediaccCard)`
  height: 100%;
`;

export const DangerCard = styled(RediaccCard)`
  border-color: ${({ theme }) => theme.colors.error};
`;

// ============================================
// ANT DESIGN BADGE WRAPPERS
// ============================================

export const PrimaryBadge = styled(RediaccBadge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.primary};
  }
`;

/**
 * Alert with spacious margin-bottom for modal contexts
 */
export const ModalAlert = styled(RediaccAlert).attrs({ spacing: 'spacious' })``;

export const TokenCopyRow = styled(SpaceCompact)`
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

export const FormItemSpaced = styled(Form.Item)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`;

export const FormItemNoMargin = styled(Form.Item)`
  && {
    margin-bottom: 0;
  }
`;

export const FormItemActions = styled(Form.Item)`
  && {
    margin: ${({ theme }) => theme.spacing.LG}px 0 0;
  }
`;

export const FormItemActionsLg = styled(Form.Item)`
  && {
    margin: ${({ theme }) => theme.spacing.XL}px 0 0;
  }
`;

// ============================================
// LEGACY / PRIMITIVES
// ============================================

// Note: ActionButton was removed from primitives as part of the Button migration.
// Components that need ActionButton should define their own styled version of Button.
