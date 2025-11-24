import styled, { css } from 'styled-components'
import { Table as AntTable } from 'antd'
import type { TableProps } from 'antd'
import type { ComponentType } from 'react'

export const Container = styled.div`
  overflow-x: auto;
  position: relative;
`

export const ContainersSection = styled.div`
  margin-bottom: 16px;
`

const StyledTableBase = styled(AntTable)<{ $removeMargins?: boolean }>`
  ${({ $removeMargins }) => $removeMargins && css`
    .ant-table.ant-table-small {
      margin-block: 0 !important;
      margin-inline: 0 !important;
    }
  `}
`

export const StyledTable = StyledTableBase as ComponentType<TableProps<any> & { $removeMargins?: boolean }>
