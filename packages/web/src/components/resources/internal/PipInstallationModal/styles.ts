import styled from 'styled-components';
import { RediaccButton } from '@/components/ui/Button';
import { RediaccText } from '@/components/ui/Text';
import { RediaccStack } from '@/components/ui';

export const CommandContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const CommandDescription = styled(RediaccText)`
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const CommandBox = styled.div`
  background: ${({ theme }) => theme.colors.bgSecondary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

export const CommandCode = styled(RediaccText).attrs({ size: 'sm' })<{
  $isComment?: boolean;
  $isCommand?: boolean;
}>`
  && {
    background: transparent;
    border: none;
    color: ${({ $isComment, $isCommand, theme }) =>
      $isComment
        ? theme.colors.textTertiary
        : $isCommand
          ? theme.colors.primary
          : theme.colors.textPrimary};
    font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
  }
`;

export const CopyButton = styled(RediaccButton).attrs({ size: 'sm' })`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

export const ContentSpace = styled(RediaccStack).attrs({ direction: 'vertical' })`
  width: 100%;
`;

export const NotesList = styled.ul`
  margin-bottom: 0;
  padding-left: 20px;
`;
