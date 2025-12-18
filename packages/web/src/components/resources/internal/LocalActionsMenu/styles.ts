import styled from 'styled-components';
import { RediaccButton, RediaccText } from '@/components/ui';

export const TriggerButton = styled(RediaccButton)`
  && {
    display: inline-flex;
    align-items: center;
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;

export const MenuLabel = styled(RediaccText).attrs({ size: 'sm' })``;
