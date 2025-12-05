import styled, { keyframes } from 'styled-components';
import { Modal, Segmented, Alert, Space, Typography, Tag, Button, Card, Row } from 'antd';

const { Title, Text } = Typography;

// Animations - only the ones actually used
const fadeIn = keyframes`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

// Styled Modal - clean and simple
export const StyledModal = styled(Modal)`
  &.ant-modal {
    max-width: 1200px;
    width: 1200px;
  }
  
  .ant-modal-content {
    animation: ${fadeIn} 0.3s ease-in-out;
  }
  
  .ant-modal-header {
    padding: ${({ theme }) => theme.spacing.MD}px ${({ theme }) => theme.spacing.LG}px;
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
  
  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.LG}px;
    max-height: 80vh;
    overflow-y: auto;
  }
  
  .ant-modal-footer {
    padding: ${({ theme }) => theme.spacing.MD}px ${({ theme }) => theme.spacing.LG}px;
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const ModeSegmented = styled(Segmented)`
  min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
`;

export const SpacedAlert = styled(Alert)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const FullWidthSpace = styled(Space)`
  width: 100%;
`;

export const CenteredMessage = styled.div`
  text-align: center;
`;

export const NoMarginTitle = styled(Title)`
  && {
    margin: 0;
  }
`;

export const NoteWrapper = styled.div`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const KeyInfoCard = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  background: ${({ theme }) => theme.colors.bgSecondary};
`;

export const KeyInfoValue = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const CaptionText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  }
`;

export const ItalicCaption = styled(CaptionText)`
  && {
    font-style: italic;
    display: block;
    text-align: center;
  }
`;

export const CodeText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const SmallStatusTag = styled(Tag)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    line-height: 1.2;
  }
`;

export const ScrollContainer = styled.div`
  max-height: 200px;
  overflow: auto;
  padding-right: ${({ theme }) => theme.spacing.XS}px;
`;

export const ScrollItem = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const SectionMargin = styled.div<{ $top?: number; $bottom?: number }>`
  ${({ $top }) => ($top !== undefined ? `margin-top: ${$top}px;` : '')}
  ${({ $bottom }) => ($bottom !== undefined ? `margin-bottom: ${$bottom}px;` : '')}
`;

export const CenteredFooter = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  text-align: center;
`;

export const SpacedCard = styled(Card)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ActionButton = styled(Button)<{ $bold?: boolean; $large?: boolean }>`
  && {
    font-weight: ${({ theme, $bold }) => ($bold ? theme.fontWeight.SEMIBOLD : theme.fontWeight.MEDIUM)};
    font-size: ${({ theme, $large }) => ($large ? theme.fontSize.SM : theme.fontSize.CAPTION)}px;
  }
`;

export const InfoList = styled.ul<{ $top?: number; $bottom?: number }>`
  padding-left: ${({ theme }) => theme.spacing.LG}px;
  ${({ $top }) => ($top !== undefined ? `margin-top: ${$top}px;` : '')}
  ${({ $bottom }) => ($bottom !== undefined ? `margin-bottom: ${$bottom}px;` : '')}
`;

export const CenteredRow = styled(Row)`
  text-align: center;
`;

export const StatusText = styled(Text)<{ $color?: string }>`
  && {
    color: ${({ $color, theme }) => $color || theme.colors.textPrimary};
    text-transform: capitalize;
  }
`;

// Modal title components
export const ModalTitleContainer = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  width: 100%;
  gap: ${({ theme }) => theme.spacing.MD}px;
  padding-right: ${({ theme }) => theme.spacing.XL}px;
`;

export const ModalTitleLeft = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex: 1;
  min-width: 0;
`;

export const ModalTitleRight = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: ${({ theme }) => theme.spacing.XS}px;
  flex-shrink: 0;
`;

export const LastFetchedText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  white-space: nowrap;
`;

export const ConsoleOutputContainer = styled.div<{ $theme: string }>`
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border: 1px solid ${({ theme }) => theme.colors.borderPrimary};
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  height: 400px;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: ${({ theme }) => theme.colors.textSecondary};
  }
`;
