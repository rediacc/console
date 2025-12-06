/**
 * Form layout components
 *
 * Components for form layouts:
 * - InlineFormRow: Horizontal form layout with wrapping
 * - ControlStack: Vertical stack for form controls
 * - InputSlot: Wrapper for form inputs
 * - ActionBar: Horizontal bar for actions
 * - ContentSection: Generic content section
 */

import styled from 'styled-components';
import {
  ControlStack as PrimitiveControlStack,
  InputSlot as PrimitiveInputSlot,
  ActionBar as PrimitiveActionBar,
  ContentSection as PrimitiveContentSection,
} from '@/styles/primitives';

export const ControlStack = PrimitiveControlStack;
export const InputSlot = PrimitiveInputSlot;
export const ActionBar = PrimitiveActionBar;
export const ContentSection = PrimitiveContentSection;

/**
 * InlineFormRow - Horizontal form layout with wrapping
 */
export const InlineFormRow = styled.div`
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: flex-start;
`;
