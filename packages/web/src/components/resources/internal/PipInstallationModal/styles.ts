import styled from 'styled-components';
import { RediaccButton } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';

export const CommandContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const CommandBox = styled.div`
  background: ${({ theme }) => theme.colors.bgSecondary};
  ${borderedCard('borderSecondary', 'SM')}
  padding: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

export const CopyButton = styled(RediaccButton).attrs({ size: 'sm' })`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

export const NotesList = styled.ul`
  margin-bottom: 0;
  padding-left: 20px;
`;
