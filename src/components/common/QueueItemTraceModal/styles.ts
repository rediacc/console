import styled, { keyframes } from 'styled-components'
import { Modal } from 'antd'

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
  max-width: 1200px;
  width: 90% !important;
  
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
  
  @media (max-width: 768px) {
    max-width: 100%;
    width: 100%;
    margin: 0;
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
  background-color: ${({ $theme }) => $theme === 'dark' ? '#1f1f1f' : '#f5f5f5'};
  border: 1px solid ${({ $theme }) => $theme === 'dark' ? '#303030' : '#d9d9d9'};
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
