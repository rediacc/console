import styled from 'styled-components';

export { RediaccModal } from './RediaccModal';
export { fadeInAnimation, resolveModalWidth } from './RediaccModal.styles';
export type { ModalSize, ModalVariant, RediaccModalProps } from './RediaccModal.types';

export const ModalStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`;

export const ModalStackLarge = styled(ModalStack)`
  gap: ${({ theme }) => theme.spacing.LG}px;
`;

export const ModalActions = styled.div`
  width: 100%;
  display: flex;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;
