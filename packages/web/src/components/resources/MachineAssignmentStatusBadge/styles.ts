import styled from 'styled-components';
import { RediaccTag } from '@/components/ui';

export const AssignmentBadge = styled(RediaccTag)`
  text-transform: none;
`;

export const AssignmentTag = styled(RediaccTag)`
  && {
    text-transform: none;
  }
`;

export const TooltipText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;
