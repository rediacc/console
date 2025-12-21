import { Button, Tooltip } from 'antd';
import React, { useEffect, useRef, useState } from 'react';
import { ContainerDetailPanel } from '@/components/resources/internal/ContainerDetailPanel';
import { MachineVaultStatusPanel } from '@/components/resources/internal/MachineVaultStatusPanel';
import { RepositoryDetailPanel } from '@/components/resources/internal/RepositoryDetailPanel';
import type { Machine, PluginContainer, Repository } from '@/types';
import {
  ContainerOutlined,
  DesktopOutlined,
  DoubleLeftOutlined,
  InboxOutlined,
} from '@/utils/optimizedIcons';

interface ContainerData {
  id: string;
  name: string;
  image: string;
  command: string;
  created: string;
  status: string;
  state: string;
  ports: string;
  port_mappings?: Array<{
    host?: string;
    host_port?: string;
    container_port: string;
    protocol: string;
  }>;
  labels: string;
  mounts: string;
  networks: string;
  size: string;
  repository: string;
  cpu_percent: string;
  memory_usage: string;
  memory_percent: string;
  net_io: string;
  block_io: string;
  pids: string;
}

type ResourceType = 'machine' | 'repository' | 'container';

interface UnifiedDetailPanelProps {
  type: ResourceType;
  data: Machine | Repository | ContainerData | PluginContainer | null;
  visible: boolean;
  onClose: () => void;
  splitWidth: number;
  onSplitWidthChange: (width: number) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  collapsedWidth?: number;
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
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const [currentData, setCurrentData] = useState(data);
  const [prevData, setPrevData] = useState(data);

  if (data !== prevData) {
    setCurrentData(data);
    setPrevData(data);
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    isDragging.current = true;
    dragStartX.current = e.clientX;
    dragStartWidth.current = splitWidth;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  };

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!isDragging.current) return;

      const deltaX = dragStartX.current - event.clientX;
      const maxWidth = 800;
      const newWidth = Math.max(300, Math.min(maxWidth, dragStartWidth.current + deltaX));
      onSplitWidthChange(newWidth);
    };

    const handleMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [splitWidth, onSplitWidthChange]);

  if (!visible || !currentData) {
    return null;
  }

  const actualType: ResourceType =
    type ||
    ('machineName' in currentData
      ? 'machine'
      : 'repositoryName' in currentData
        ? 'repository'
        : 'container');

  const getResourceIcon = () => {
    switch (actualType) {
      case 'machine':
        return <DesktopOutlined />;
      case 'repository':
        return <InboxOutlined />;
      case 'container':
      default:
        return <ContainerOutlined />;
    }
  };

  const actualWidth = isCollapsed ? collapsedWidth : splitWidth;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: actualWidth,
        display: 'flex',
        flexShrink: 0,
        zIndex: 1000,
      }}
      data-testid="unified-detail-panel"
    >
      {!isCollapsed && (
        <div
          onMouseDown={handleMouseDown}
          data-testid="unified-detail-resize-handle"
          style={{
            position: 'absolute',
            left: -3,
            top: 0,
            bottom: 0,
            width: 8,
            cursor: 'ew-resize',
            zIndex: 10,
          }}
        >
          <div style={{ position: 'absolute', left: 2, top: 0, bottom: 0, width: 2 }} />
        </div>
      )}

      {isCollapsed ? (
        <div
          data-testid="unified-detail-collapsed"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'flex-start',
            width: '100%',
          }}
        >
          <Tooltip title="Expand Panel" placement="left">
            <Button
              type="text"
              icon={<DoubleLeftOutlined />}
              onClick={onToggleCollapse}
              data-testid="unified-detail-expand-button"
              aria-label="Expand Panel"
            />
          </Tooltip>
          <span style={{ fontSize: 16 }}>{getResourceIcon()}</span>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }} data-testid="unified-detail-content">
          {actualType === 'machine' ? (
            <MachineVaultStatusPanel
              machine={currentData as Machine}
              visible={visible}
              onClose={onClose}
              splitView
            />
          ) : actualType === 'repository' ? (
            <RepositoryDetailPanel
              repository={currentData as Repository}
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
        </div>
      )}
    </div>
  );
};
