import styled from 'styled-components';
import { ContentStack, ActionsRow } from '@/components/common/styled';
import { RediaccButton, RediaccCard, RediaccAlert } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';

export { ContentStack, ActionsRow };

export const DividerContent = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const SectionTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const SectionCard = styled(RediaccCard)`
  && {
    ${borderedCard()}
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const AlertWrapper = styled(RediaccAlert)`
  && {
    ${borderedCard()}
    padding: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ActionButton = styled(RediaccButton).attrs({
  size: 'sm',
})`
  && {
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export { LoadingState } from '@/styles/primitives';
