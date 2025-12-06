import styled from 'styled-components';
import { RediaccButton } from '@/components/ui/Button';
import { RediaccText } from '@/components/ui/Text';

export const TriggerButton = styled(RediaccButton)`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const MenuLabel = styled(RediaccText).attrs({ size: 'sm' })``;
