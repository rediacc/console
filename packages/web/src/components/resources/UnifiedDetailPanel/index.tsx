import React, { useEffect, useRef, useState } from 'react';
import { Button, Flex, Tooltip, Typography } from 'antd';
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
    <Flex
      className="fixed flex flex-shrink-0"
      // eslint-disable-next-line no-restricted-syntax
      style={{
        top: 0,
        right: 0,
        bottom: 0,
        width: actualWidth,
        zIndex: 1000,
      }}
      data-testid="unified-detail-panel"
    >
      {!isCollapsed && (
        <Flex
          onMouseDown={handleMouseDown}
          data-testid="unified-detail-resize-handle"
          className="absolute cursor-ew-resize"
          // eslint-disable-next-line no-restricted-syntax
          style={{
            left: -3,
            top: 0,
            bottom: 0,
            width: 8,
            zIndex: 10,
          }}
        >
          <Flex
            className="absolute"
            // eslint-disable-next-line no-restricted-syntax
            style={{ left: 2, top: 0, bottom: 0, width: 2 }}
          />
        </Flex>
      )}

      {isCollapsed ? (
        <Flex
          vertical
          align="center"
          justify="flex-start"
          data-testid="unified-detail-collapsed"
          className="w-full"
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
          <Typography.Text
            // eslint-disable-next-line no-restricted-syntax
            style={{ fontSize: 16 }}
          >
            {getResourceIcon()}
          </Typography.Text>
        </Flex>
      ) : (
        <Flex
          className="flex-1 overflow-auto overflow-x-hidden"
          data-testid="unified-detail-content"
        >
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
        </Flex>
      )}
    </Flex>
  );
};
