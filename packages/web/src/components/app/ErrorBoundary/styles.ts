import styled from 'styled-components';
import { FlexColumn } from '@/styles/primitives';

export const FallbackContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.XL}px;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: ${({ theme }) => theme.dimensions.CONTENT_MIN_HEIGHT}px;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
`;

export const ErrorDetails = styled.details`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  text-align: left;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  font-family: ${({ theme }) => theme.fontFamily.MONO};
  white-space: pre-wrap;
  border: 1px dashed ${({ theme }) => theme.colors.borderSecondary};
`;

export const ErrorSummary = styled.summary`
  cursor: pointer;
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const ErrorContent = styled(FlexColumn).attrs({ $gap: 'XS' })`
  strong {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;
