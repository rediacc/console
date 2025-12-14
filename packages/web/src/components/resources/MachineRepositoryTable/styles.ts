import styled from 'styled-components';
import { ExpandIcon as BaseExpandIcon } from '@/styles/primitives';

const withAlpha = (color: string, alphaHex: string) =>
  color.startsWith('#') ? `${color}${alphaHex}` : color;

export const Container = styled.div`
  overflow-x: auto;
  position: relative;
`;

export const LoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  background-color: ${({ theme }) => withAlpha(theme.colors.bgPrimary, 'CC')};
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: ${({ theme }) => theme.zIndex.OVERLAY};
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
`;

export const MachineHeader = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding-top: ${({ theme }) => theme.spacing.MD}px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  padding-bottom: ${({ theme }) => theme.spacing.SM}px;
`;

export const MachineTitle = styled.div`
  margin: 0;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const MachineIcon = styled.span`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
  color: ${({ theme }) => theme.colors.iconSystem};
`;

export const ExpandedRowContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px 0;
  position: relative;
`;

export const ExpandedRowLoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  background-color: ${({ theme }) => withAlpha(theme.colors.bgPrimary, 'CC')};
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: ${({ theme }) => theme.zIndex.OVERLAY};
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
`;

export const ContainersSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const PluginsSection = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`;

/** Wrapper for repository table row styling */
export const TableStyleWrapper = styled.div`
  .Repository-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.HOVER};
  }

  .Repository-row:hover {
    background-color: ${({ theme }) => theme.colors.bgHover};
  }

  .Repository-row--highlighted,
  .Repository-row--highlighted:hover {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }

  .Repository-fork-row {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
  }

  .Repository-fork-row:hover {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
  }
`;

export const SystemContainersWrapper = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.XL}px;
`;

export const SystemContainersTitle = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  margin-top: ${({ theme }) => theme.spacing.XL}px;
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
