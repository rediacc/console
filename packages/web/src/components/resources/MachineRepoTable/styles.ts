import styled, { css } from 'styled-components';
import { Table as AntTable } from 'antd';
import type { TableProps } from 'antd';
import type { ComponentType } from 'react';
import { ExpandIcon as BaseExpandIcon } from '@/styles/primitives';
import { RediaccText } from '@/components/ui/Text';

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
  z-index: 10;
  border-radius: 4px;
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
  font-size: 20px;
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
  z-index: 10;
  border-radius: 4px;
`;

export const ContainersSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const PluginsSection = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`;

const StyledTableBase = styled(AntTable)<{ $removeMargins?: boolean }>`
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
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

export const StatusIcon = styled.span<{ $color: string }>`
  font-size: ${({ theme }) => theme.fontSize.LG}px;
  color: ${(props) => props.$color};
`;

export const ExpandIcon = styled(BaseExpandIcon).attrs<{
  $isExpanded: boolean;
  $visible: boolean;
}>(({ $isExpanded, $visible }) => ({
  $expanded: $isExpanded,
  $visible,
}))<{ $isExpanded: boolean; $visible: boolean }>`
  width: 12px;
`;

export const PortText = styled(RediaccText).attrs({
  size: 'xs',
})``;
