import styled from 'styled-components';
import { RediaccButton, RediaccText } from '@/components/ui';
import { BaseModal, ModalBody } from '@/styles/primitives';

export const StyledModal = styled(BaseModal)`
  .ant-modal-content {
  }
`;

export const ContentStack = styled(ModalBody)`
`;

export const SessionExpiredTitle = styled(RediaccText)`
  && {
    color: var(--color-error);
  }
`;

export const CountdownCard = styled.div`
  background: ${({ theme }) => theme.colors.bgPrimary};
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  text-align: center;
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
