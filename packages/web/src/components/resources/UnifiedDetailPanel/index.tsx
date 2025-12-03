import React, { useEffect, useRef, useState } from 'react'
import { Tooltip } from 'antd'
import { DoubleLeftOutlined, DesktopOutlined, InboxOutlined, ContainerOutlined } from '@/utils/optimizedIcons'
import { MachineVaultStatusPanel } from '../internal/MachineVaultStatusPanel'
import { RepoDetailPanel } from '../internal/RepoDetailPanel'
import { ContainerDetailPanel } from '../internal/ContainerDetailPanel'
import type { Machine, Repo } from '@/types'
import {
  CollapsedIcon,
  CollapsedPanel,
  ExpandedContent,
  PanelContainer,
  ResizeHandle,
  ResizeIndicator,
  ToggleButton,
} from './styles'

interface ContainerData {
  id: string
  name: string
  image: string
  command: string
  created: string
  status: string
  state: string
  ports: string
  port_mappings?: Array<{
    host?: string
    host_port?: string
    container_port: string
    protocol: string
  }>
  labels: string
  mounts: string
  networks: string
  size: string
  repo: string
  cpu_percent: string
  memory_usage: string
  memory_percent: string
  net_io: string
  block_io: string
  pids: string
}

type ResourceType = 'machine' | 'repo' | 'container'

interface UnifiedDetailPanelProps {
  type: ResourceType
  data: Machine | Repo | ContainerData | null
  visible: boolean
  onClose: () => void
  splitWidth: number
  onSplitWidthChange: (width: number) => void
  isCollapsed?: boolean
  onToggleCollapse?: () => void
  collapsedWidth?: number
}

export const UnifiedDetailPanel: React.FC<UnifiedDetailPanelProps> = ({
  type,
  data,
  visible,
  onClose,
  splitWidth,
  onSplitWidthChange,
  isCollapsed = false,
  onToggleCollapse,
  collapsedWidth = 50,
}) => {
  const isDragging = useRef(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

  const [currentData, setCurrentData] = useState(data)
  const [prevData, setPrevData] = useState(data)

  if (data !== prevData) {
    setCurrentData(data)
    setPrevData(data)
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    isDragging.current = true
    dragStartX.current = e.clientX
    dragStartWidth.current = splitWidth
    document.body.style.cursor = 'ew-resize'
    document.body.style.userSelect = 'none'
    e.preventDefault()
  }

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isDragging.current) return

      const deltaX = dragStartX.current - event.clientX
      const maxWidth = 800
      const newWidth = Math.max(300, Math.min(maxWidth, dragStartWidth.current + deltaX))
      onSplitWidthChange(newWidth)
    }

    const handleMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [splitWidth, onSplitWidthChange])

  if (!visible || !currentData) {
    return null
  }

  const actualType: ResourceType =
    type ||
    ('machineName' in currentData
      ? 'machine'
      : 'repoName' in currentData
        ? 'repo'
        : 'container')

  const getResourceIcon = () => {
    switch (actualType) {
      case 'machine':
        return <DesktopOutlined />
      case 'repo':
        return <InboxOutlined />
      case 'container':
      default:
        return <ContainerOutlined />
    }
  }

  const actualWidth = isCollapsed ? collapsedWidth : splitWidth

  return (
    <PanelContainer $width={actualWidth} $opacity={1} data-testid="unified-detail-panel">
      {!isCollapsed && (
        <ResizeHandle onMouseDown={handleMouseDown} data-testid="unified-detail-resize-handle">
          <ResizeIndicator />
        </ResizeHandle>
      )}

      {isCollapsed ? (
        <CollapsedPanel data-testid="unified-detail-collapsed">
          <Tooltip title="Expand Panel" placement="left">
            <ToggleButton
              type="text"
              icon={<DoubleLeftOutlined />}
              onClick={onToggleCollapse}
              data-testid="unified-detail-expand-button"
              aria-label="Expand Panel"
            />
          </Tooltip>
          <CollapsedIcon $type={actualType}>{getResourceIcon()}</CollapsedIcon>
        </CollapsedPanel>
      ) : (
        <ExpandedContent data-testid="unified-detail-content">
          {actualType === 'machine' ? (
            <MachineVaultStatusPanel
              machine={currentData as Machine}
              visible={visible}
              onClose={onClose}
              splitView
            />
          ) : actualType === 'repo' ? (
            <RepoDetailPanel
              repo={currentData as Repo}
              visible={visible}
              onClose={onClose}
              splitView
            />
          ) : (
            <ContainerDetailPanel
              container={currentData as ContainerData}
              visible={visible}
              onClose={onClose}
              splitView
            />
          )}
        </ExpandedContent>
      )}
    </PanelContainer>
  )
}
