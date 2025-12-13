import styled from 'styled-components';
import { RediaccButton, RediaccText } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';
import { BaseModal, ModalBody } from '@/styles/primitives';

export const StyledModal = styled(BaseModal)`
  .ant-modal-content {
    ${borderedCard()}
  }
`;

export const ContentStack = styled(ModalBody)`
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const SessionExpiredTitle = styled(RediaccText)`
  && {
    margin: 0;
    color: var(--color-error);
  }
`;

export const CountdownCard = styled.div`
  background: ${({ theme }) => theme.colors.bgSecondary};
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  text-align: center;
  ${borderedCard('borderSecondary', 'MD')}
`;

export const CountdownText = styled(RediaccText)`
  && {
    color: var(--color-error);
  }
`;

export const FooterButton = styled(RediaccButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
  }
`;
