import styled from 'styled-components';
import { ExpandIcon as BaseExpandIcon } from '@/styles/primitives';

export const Container = styled.div`
  overflow-x: auto;
  position: relative;
`;

export const LoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: ${({ theme }) => theme.zIndex.OVERLAY};
`;

export const MachineHeader = styled.div`
`;

export const MachineTitle = styled.div`
`;

export const MachineIcon = styled.span`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const ExpandedRowContainer = styled.div`
  position: relative;
`;

export const ExpandedRowLoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: ${({ theme }) => theme.zIndex.OVERLAY};
`;

export const ContainersSection = styled.div`
`;

export const PluginsSection = styled.div`
`;

/** Wrapper for repository table row styling */
export const TableStyleWrapper = styled.div`
  .Repository-row {
    cursor: pointer;
  }

  .Repository-row:hover {
  }

  .Repository-row--highlighted,
  .Repository-row--highlighted:hover {
  }

  .Repository-fork-row {
  }

  .Repository-fork-row:hover {
  }
`;

export const SystemContainersWrapper = styled.div`
`;

export const SystemContainersTitle = styled.div`
`;

export const ExpandIcon = styled(BaseExpandIcon).attrs<{
  $isExpanded: boolean;
  $visible: boolean;
}>(({ $isExpanded, $visible }) => ({
  $expanded: $isExpanded,
  $visible,
}))<{ $isExpanded: boolean; $visible: boolean }>`
  width: ${({ theme }) => theme.spacing.SM_LG}px;
`;

// PortText removed - use <RediaccText size="xs"> directly if needed
