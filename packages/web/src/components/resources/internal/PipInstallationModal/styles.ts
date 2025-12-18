import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';

export const CommandContainer = styled.div`
`;

export const CommandBox = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

export const CopyButton = styled(RediaccButton)`
`;

export const NotesList = styled.ul`
`;

export const CommandDescription = styled.div`
  display: block;
`;

export const CommandText = styled.span`
  font-family: ${({ theme }) => theme.fontFamily.MONO};
`;
