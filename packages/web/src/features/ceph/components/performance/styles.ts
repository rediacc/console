import { Skeleton } from 'antd';
import styled from 'styled-components';

interface RowWrapperProps {
  $hasOnClick: boolean;
}

export const RowWrapper = styled.div<RowWrapperProps>`
  cursor: ${({ $hasOnClick }) => ($hasOnClick ? 'pointer' : 'default')};
  padding: 0 ${({ theme }) => theme.spacing.MD}px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  transition: background-color ${({ theme }) => theme.transitions.DEFAULT};
  display: flex;
  align-items: center;
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;

  &:hover {
    background-color: ${({ theme }) => theme.colors.bgHover};
  }
`;

export const TableWrapper = styled.div`
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgPrimary};

  &:focus {
    outline: 2px solid ${({ theme }) => theme.colors.primary};
    outline-offset: -2px;
  }
`;

export const HeaderWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgSecondary};
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  position: sticky;
  top: 0;
  z-index: ${({ theme }) => theme.zIndex.STICKY};
`;

export const RowContent = styled.div`
  width: 100%;
  display: flex;
  align-items: center;
`;

export const HeaderContent = styled.div`
  width: 100%;
  display: flex;
  align-items: center;
`;

export const CheckboxColumn = styled.div`
  width: 40px;
  flex-shrink: 0;
`;

export const MachineNameColumn = styled.div`
  flex: 1;
  min-width: 200px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const TeamNameColumn = styled.div`
  width: 150px;
  color: ${({ theme }) => theme.colors.textSecondary};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const StatusColumn = styled.div`
  width: 200px;
`;

export const ActionsColumn = styled.div`
  width: 150px;
  display: flex;
  justify-content: flex-end;
`;

export const LoadingRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.MD}px;
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
