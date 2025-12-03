import styled, { css } from 'styled-components'
import { Table as AntTable } from 'antd'
import type { TableProps } from 'antd'
import type { ComponentType } from 'react'
import { ExpandIcon as BaseExpandIcon } from '@/styles/primitives'

export const Container = styled.div`
  overflow-x: auto;
  position: relative;
`

export const LoadingOverlay = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border-radius: 4px;
`

export const MachineHeader = styled.div`
  margin-bottom: 16px;
  padding-top: 16px;
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 12px;
`

export const MachineTitle = styled.div`
  margin: 0;
  color: #556b2f;
`

export const MachineIcon = styled.span`
  font-size: 20px;
  color: #556b2f;
`

export const ExpandedRowContainer = styled.div`
  padding: 16px 0;
  position: relative;
`

export const ExpandedRowLoadingOverlay = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  border-radius: 4px;
`

export const ContainersSection = styled.div`
  margin-bottom: 16px;
`

export const PluginsSection = styled.div`
  margin-top: 16px;
`

const StyledTableBase = styled(AntTable)<{ $removeMargins?: boolean }>`
  ${({ $removeMargins }) => $removeMargins && css`
    .ant-table.ant-table-small {
      margin-block: 0 !important;
      margin-inline: 0 !important;
    }
  `}
`

export const StyledTable = StyledTableBase as ComponentType<TableProps<unknown> & { $removeMargins?: boolean }>

export const SystemContainersWrapper = styled.div`
  margin-bottom: 32px;
`

export const SystemContainersTitle = styled.div`
  margin-bottom: 16px;
  margin-top: 32px;
`

export const StatusIcon = styled.span<{ $color: string }>`
  font-size: 18px;
  color: ${props => props.$color};
`

export const ExpandIcon = styled(BaseExpandIcon).attrs<{
  $isExpanded: boolean
  $visible: boolean
}>(({ $isExpanded, $visible }) => ({
  $expanded: $isExpanded,
  $visible,
}))<{ $isExpanded: boolean; $visible: boolean }>`
  width: 12px;
`

export const PortText = styled.span`
  font-size: 12px;
`
