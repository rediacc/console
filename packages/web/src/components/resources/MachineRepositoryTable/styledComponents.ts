import styled from 'styled-components';
import { RediaccTag, RediaccText } from '@/components/ui';

export const SmallText = styled(RediaccText)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const GrandTag = styled(RediaccTag)`
`;

export const ModalContent = styled.div`
  display: flex;
  flex-direction: column;
`;

export const ConfirmationInput = styled.input`
  width: 100%;
`;

export const TableStateContainer = styled.div`
`;
