import styled from 'styled-components';
import { ActionsRow, ContentStack } from '@/components/common/styled';
import { RediaccAlert, RediaccButton, RediaccCard } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';

export { ContentStack, ActionsRow };

export const DividerContent = styled.div`
  display: inline-flex;
  align-items: center;
`;

export const SectionTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const SectionCard = styled(RediaccCard)`
  && {
    ${borderedCard()}
  }
`;

export const AlertWrapper = styled(RediaccAlert)`
  && {
    ${borderedCard()}
  }
`;

export const ActionButton = styled(RediaccButton)`
  && {
  }
`;

export { LoadingState } from '@/styles/primitives';

export const LabelBlock = styled.div`
  display: block;
`;
