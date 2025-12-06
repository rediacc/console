/**
 * Text components
 *
 * Styled text variants:
 * - SecondaryText, LoadingHint, WarningNote
 * - DangerText, CaptionText
 */

import styled from 'styled-components';
import { RediaccText } from '@/components/ui/Text';

export const SecondaryText = styled(RediaccText).attrs({ size: 'sm', color: 'secondary' })``;

export const LoadingHint = styled(RediaccText).attrs({ color: 'secondary' })`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const WarningNote = styled(RediaccText)`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const DangerText = styled(RediaccText).attrs({ color: 'danger' })``;

export const CaptionText = styled(RediaccText).attrs({ variant: 'caption', color: 'secondary' })``;
