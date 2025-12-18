import { Skeleton } from 'antd';
import styled from 'styled-components';

interface RowWrapperProps {
  $hasOnClick: boolean;
}

export const RowWrapper = styled.div<RowWrapperProps>`
  cursor: ${({ $hasOnClick }) => ($hasOnClick ? 'pointer' : 'default')};
  display: flex;
  align-items: center;
  min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;

  &:hover {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const TableWrapper = styled.div`
  overflow: hidden;
  background: ${({ theme }) => theme.colors.bgContainer};

  &:focus {
    outline: ${({ theme }) => theme.dimensions.BORDER_WIDTH_THICK}px solid
      ${({ theme }) => theme.colors.primary};
    outline-offset: -${({ theme }) => theme.dimensions.BORDER_WIDTH_THICK}px;
  }
`;

export const HeaderWrapper = styled.div`
  background: ${({ theme }) => theme.colors.bgPrimary};
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
  width: ${({ theme }) => theme.dimensions.CHECKBOX_COLUMN_WIDTH}px;
  flex-shrink: 0;
`;

export const MachineNameColumn = styled.div`
  flex: 1;
  min-width: ${({ theme }) => theme.dimensions.MACHINE_NAME_MIN_WIDTH}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const TeamNameColumn = styled.div`
  width: ${({ theme }) => theme.dimensions.TEAM_COLUMN_WIDTH}px;
  color: ${({ theme }) => theme.colors.textSecondary};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const StatusColumn = styled.div`
  width: ${({ theme }) => theme.dimensions.STATUS_COLUMN_WIDTH}px;
`;

export const ActionsColumn = styled.div`
  width: ${({ theme }) => theme.dimensions.ACTIONS_COLUMN_WIDTH}px;
  display: flex;
  justify-content: flex-end;
`;

export const LoadingRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
`;

export const LoadingContainer = styled.div`
`;

// LazyAssignmentStatus styles
export const LazyLoadingContainer = styled.div`
  height: ${({ theme }) => theme.dimensions.SKELETON_HEIGHT}px;
  width: ${({ theme }) => theme.dimensions.SKELETON_WIDTH}px;
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
  display: flex;
  align-items: center;
  justify-content: center;
`;

export const StyledSkeletonInput = styled(Skeleton.Input)`
  && {
    width: ${({ theme }) => theme.dimensions.SKELETON_WIDTH}px;
    height: ${({ theme }) => theme.dimensions.SKELETON_HEIGHT}px;
  }
`;

export const StyledSkeletonButton = styled(Skeleton.Button)`
  && {
  }
`;
