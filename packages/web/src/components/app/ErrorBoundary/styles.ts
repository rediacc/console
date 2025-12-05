import styled from 'styled-components';

export const FallbackContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.XL}px;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
`;

export const ErrorDetails = styled.details`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  text-align: left;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  font-family: 'Monaco', 'Menlo', 'Consolas', 'Courier New', monospace;
  white-space: pre-wrap;
  border: 1px dashed ${({ theme }) => theme.colors.borderSecondary};
`;

export const ErrorSummary = styled.summary`
  cursor: pointer;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const ErrorContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;

  strong {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;
