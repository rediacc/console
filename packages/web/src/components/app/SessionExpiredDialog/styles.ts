import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';
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

export const CountdownCard = styled.div`
  background: ${({ theme }) => theme.colors.bgSecondary};
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  text-align: center;
  ${borderedCard('borderSecondary', 'MD')}
`;

export const FooterButton = styled(RediaccButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_LG}px;
  }
`;
