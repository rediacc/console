import type { ComponentType } from 'react';
import { Table as AntTable } from 'antd';
import styled, { css } from 'styled-components';
import { borderedCard } from '@/styles/mixins';
import { ExpandIcon as BaseExpandIcon } from '@/styles/primitives';
import type { TableProps } from 'antd';

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

const StyledTableBase = styled(AntTable)<{ $removeMargins?: boolean }>`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  ${borderedCard()}
  overflow: hidden;

  .ant-table {
    border-radius: inherit;
  }

  .Repo-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.HOVER};
  }

  .Repo-row:hover {
    background-color: ${({ theme }) => theme.colors.bgHover};
  }

  .Repo-row--highlighted,
  .Repo-row--highlighted:hover {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }

  .Repo-fork-row {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
  }

  .Repo-fork-row:hover {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
  }

  ${({ $removeMargins }) =>
    $removeMargins &&
    css`
      .ant-table.ant-table-small {
        margin-block: 0;
        margin-inline: 0;
      }
    `}
`;

export const StyledTable = StyledTableBase as ComponentType<
  TableProps<unknown> & { $removeMargins?: boolean }
>;

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
