import styled, { keyframes } from 'styled-components';
import { Modal } from 'antd';

// Fade in animation for modal
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
  .ant-modal-content {
    animation: ${fadeIn} 0.3s ease-in-out;
  }
  
  .ant-modal-header {
    padding: ${({ theme }) => theme.spacing.MD}px ${({ theme }) => theme.spacing.LG}px;
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
  
  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.LG}px;
  }
  
  .ant-modal-footer {
    padding: ${({ theme }) => theme.spacing.MD}px ${({ theme }) => theme.spacing.LG}px;
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
`;

// Loading container
export const LoadingContainer = styled.div`
  text-align: center;
  padding: ${({ theme }) => theme.spacing.XXXL}px 0;
`;

export const LoadingText = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

// Summary section
export const SummaryContainer = styled.div`
  width: 100%;
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const SummaryRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

export const SummaryStats = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.XL}px;
`;

export const StatItem = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`;

export const StatValue = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  font-size: ${({ theme }) => theme.fontSize.XL}px;
`;

// Icon wrappers with colors
