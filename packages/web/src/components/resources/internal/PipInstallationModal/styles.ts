import styled from 'styled-components';
import { Typography, Button, Space } from 'antd';

const { Text } = Typography;

export const CommandContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const CommandDescription = styled(Text)`
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing['0.5']}px;
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

export const CommandCode = styled(Text)<{ $isComment?: boolean; $isCommand?: boolean }>`
  background: transparent !important;
  border: none !important;
  color: ${({ $isComment, $isCommand, theme }) =>
    $isComment
      ? theme.colors.textTertiary
      : $isCommand
        ? theme.colors.primary
        : theme.colors.textPrimary} !important;
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const CopyButton = styled(Button)`
  margin-left: ${({ theme }) => theme.spacing.XS}px;
`;

export const ContentSpace = styled(Space)`
  width: 100%;
`;

export const NotesList = styled.ul`
  margin-bottom: 0;
  padding-left: 20px;
`;
