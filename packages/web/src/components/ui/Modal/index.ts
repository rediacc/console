import styled from 'styled-components';

export { RediaccModal } from './RediaccModal';
export { resolveModalWidth } from './RediaccModal.styles';
export type { ModalSize, ModalVariant, RediaccModalProps } from './RediaccModal.types';

export const ModalStack = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const ModalStackLarge = styled(ModalStack)`
`;

export const ModalActions = styled.div`
  width: 100%;
  display: flex;
  justify-content: flex-end;
`;
