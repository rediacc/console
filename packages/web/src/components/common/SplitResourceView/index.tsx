import React from 'react';
import { Drawer, Flex, Grid, Modal } from 'antd';
import { ContainerDetailPanel } from '@/components/resources/internal/ContainerDetailPanel';
import { MachineTable } from '@/components/resources/internal/MachineTable';
import { MachineVaultStatusPanel } from '@/components/resources/internal/MachineVaultStatusPanel';
import { RepositoryDetailPanel } from '@/components/resources/internal/RepositoryDetailPanel';
import { usePanelWidth } from '@/hooks/usePanelWidth';
import { Machine, Repository } from '@/types';

export interface ContainerData {
  id: string;
  name: string;
  image: string;
  command: string;
  created: string;
  status: string;
  state: string;
  ports: string;
  port_mappings?: {
    host?: string;
    host_port?: string;
    container_port: string;
    protocol: string;
  }[];
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

interface SplitResourceViewProps {
  type: 'machine' | 'repository';
  teamFilter?: string | string[];
  showFilters?: boolean;
  showActions?: boolean;
  onCreateMachine?: () => void;
  onEditMachine?: (machine: Machine) => void;
  onVaultMachine?: (machine: Machine) => void;
  onFunctionsMachine?: (machine: Machine, functionName?: string) => void;
  onDeleteMachine?: (machine: Machine) => void;
  onCreateRepository?: (machine: Machine, repositoryGuid?: string) => void;
  enabled?: boolean;
  className?: string;
  expandedRowKeys?: string[];
  onExpandedRowsChange?: (keys: string[]) => void;
  refreshKeys?: Record<string, number>;
  onQueueItemCreated?: (taskId: string, machineName: string) => void;
  selectedResource: Machine | Repository | ContainerData | null;
  onResourceSelect: (resource: Machine | Repository | ContainerData | null) => void;
  isPanelCollapsed?: boolean;
  onTogglePanelCollapse?: () => void;
}

export const SplitResourceView: React.FC<SplitResourceViewProps> = (props) => {
  const { type, selectedResource, onResourceSelect } = props;

  const panelWidth = usePanelWidth();
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;

  const handleMachineSelect = (machine: Machine) => {
    onResourceSelect(machine);
  };

  const handlePanelClose = () => {
    onResourceSelect(null);
  };

  const getResourceType = () => {
    if (!selectedResource) return 'machine';
    if ('machineName' in selectedResource) return 'machine';
    if ('repositoryName' in selectedResource) return 'repository';
    return 'container';
  };

  const renderPanelContent = () => {
    if (!selectedResource) return null;

    const resourceType = getResourceType();

    if (resourceType === 'machine') {
      return (
        <MachineVaultStatusPanel
          machine={selectedResource as Machine}
          visible
          onClose={handlePanelClose}
          splitView
        />
      );
    }
    if (resourceType === 'repository') {
      return (
        <RepositoryDetailPanel
          repository={selectedResource as Repository}
          visible
          onClose={handlePanelClose}
          splitView
        />
      );
    }
    return (
      <ContainerDetailPanel
        container={selectedResource as ContainerData}
        visible
        onClose={handlePanelClose}
        splitView
      />
    );
  };

  if (type === 'machine') {
    return (
      <Flex
        data-testid="split-resource-view-container"
        className="h-full w-full relative overflow-hidden"
      >
        <Flex data-testid="split-resource-view-left-panel" className="w-full h-full overflow-auto">
          <MachineTable
            {...props}
            onRowClick={handleMachineSelect}
            selectedMachine={selectedResource as Machine}
          />
        </Flex>

        {isMobile ? (
          <Modal
            open={!!selectedResource}
            onCancel={handlePanelClose}
            footer={null}
            width="100%"
            data-testid="split-resource-view-modal"
            centered
          >
            {renderPanelContent()}
          </Modal>
        ) : (
          <Drawer
            open={!!selectedResource}
            onClose={handlePanelClose}
            width={panelWidth}
            placement="right"
            mask
            data-testid="split-resource-view-drawer"
          >
            {renderPanelContent()}
          </Drawer>
        )}
      </Flex>
    );
  }

  return null;
};
