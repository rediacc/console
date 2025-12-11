import { Skeleton } from 'antd';
import styled from 'styled-components';

interface RowWrapperProps {
  $hasOnClick: boolean;
}

export const RowWrapper = styled.div<RowWrapperProps>`
  cursor: ${({ $hasOnClick }) => ($hasOnClick ? 'pointer' : 'default')};
  border-bottom: 1px solid var(--color-border-secondary);
  transition: background-color 0.2s ease;
`;

export const TableWrapper = styled.div``;

export const HeaderWrapper = styled.div`
  position: sticky;
  top: 0;
  z-index: ${({ theme }) => theme.zIndex.STICKY};
  border-bottom: 1px solid var(--color-border-secondary);
`;

export const LoadingContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px;
`;

// LazyAssignmentStatus styles
export const LazyLoadingContainer = styled.div`
  height: 22px;
  width: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
`;

export const FlexCenterContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
`;

export const LoadingMoreContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px;
  display: flex;
  align-items: center;
  justify-content: center;
`;

export const StyledSkeletonInput = styled(Skeleton.Input)`
  && {
    width: 120px;
    height: 22px;
    border-radius: var(--border-radius-sm);
  }
`;

export const StyledSkeletonButton = styled(Skeleton.Button)`
  && {
    border-radius: var(--border-radius-sm);
  }
`;
