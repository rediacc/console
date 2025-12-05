import styled, { css } from 'styled-components';
import { Table as AntTable, Typography } from 'antd';
import type { TableProps } from 'antd';
import React from 'react';

const { Title } = Typography;

export const Container = styled.div`
  overflow-x: auto;
  position: relative;
`;

export const ContainersSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const PluginContainersSection = styled(ContainersSection)`
  margin-top: ${({ theme }) => theme.spacing.LG}px;
`;

export const EmptyState = styled.div`
  padding: ${({ theme }) => `${theme.spacing.XXL}px 0`};
  text-align: center;
`;

const StyledTableBase = styled(AntTable)<{ $removeMargins?: boolean }>`
  ${({ $removeMargins }) =>
    $removeMargins &&
    css`
      .ant-table.ant-table-small {
        margin-block: 0;
        margin-inline: 0;
      }
    `}

  .repo-container-row td {
    transition: background-color ${({ theme }) => theme.transitions.DEFAULT};
  }

  .repo-container-row--clickable {
    cursor: pointer;
  }

  .repo-container-row--clickable:hover td {
    background-color: ${({ theme }) => theme.colors.bgHover};
  }

  .repo-container-row--selected td {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }
`;

export const StyledTable = StyledTableBase as <T = unknown>(
  props: TableProps<T> & { $removeMargins?: boolean }
) => React.ReactElement;

export const SectionTitle = styled(Title)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;
