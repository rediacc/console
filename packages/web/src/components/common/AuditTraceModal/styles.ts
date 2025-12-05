import styled from 'styled-components';
import { FadeInModal } from '@/styles/primitives';

export const StyledModal = FadeInModal;

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
