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
  padding: ${({ theme }) => theme.spacing.SM}px;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  text-align: left;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  font-family: ${({ theme }) => theme.fontFamily.MONO};
  white-space: pre-wrap;
`;

export const ErrorSummary = styled.summary`
  cursor: pointer;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const ErrorContent = styled(FlexColumn).attrs({})`
  strong {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;
