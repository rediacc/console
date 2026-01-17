import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Empty, Flex, type MenuProps, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { useGetTeamMachines, useGetTeamRepositories } from '@/api/api-hooks.generated';
import AuditTraceModal from '@/components/common/AuditTraceModal';
import { MobileCard } from '@/components/common/MobileCard';
import { RemoteFileBrowserModal } from '@/components/common/RemoteFileBrowserModal';
import { ResourceActionsDropdown } from '@/components/common/ResourceActionsDropdown';
import ResourceListView from '@/components/common/ResourceListView';
import { MachineVaultStatusPanel } from '@/components/resources/internal/MachineVaultStatusPanel';
import { featureFlags } from '@/config/featureFlags';
import { AssignToClusterModal } from '@/features/ceph/components/modals/AssignToClusterModal';
import { RemoveFromClusterModal } from '@/features/ceph/components/modals/RemoveFromClusterModal';
import { ViewAssignmentStatusModal } from '@/features/ceph/components/modals/ViewAssignmentStatusModal';
import { useDialogState, useTraceModal } from '@/hooks/useDialogState';
import { useDynamicPageSize } from '@/hooks/useDynamicPageSize';
import { getMachineRepositories as coreGetMachineRepositories } from '@/platform';
import { useLocalizedFunctions } from '@/services/functionsService';
import { usePingFunction } from '@/services/pingService';
import { RootState } from '@/store/store';
import type { Machine } from '@/types';
import {
  DeleteOutlined,
  DesktopOutlined,
  EditOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  FunctionOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons';
import { buildMachineTableColumns, type MachineFunctionAction } from './columns';
import { BulkActionsToolbar } from './components/BulkActionsToolbar';
import { GroupedMachineCard } from './components/GroupedMachineCard';
import { ViewToggleButtons } from './components/ViewToggleButtons';
import { useGroupedMachines } from './hooks/useGroupedMachines';
import type { GroupByMode, MachineTableProps } from './types';

export const MachineTable: React.FC<MachineTableProps> = ({
  teamFilter,
  showActions = true,
  className = '',
  onEditMachine,
  onFunctionsMachine,
  onDeleteMachine,
  onQueueItemCreated,
  onRowClick,
  selectedMachine: _externalSelectedMachine,
}) => {
  const { t } = useTranslation(['machines', 'common', 'functions', 'resources']);
  const navigate = useNavigate();
  const uiMode = useSelector((state: RootState) => state.ui.uiMode);
  const isExpertMode = uiMode === 'expert';
  const { executePingForMachineAndWait } = usePingFunction();
  const tableContainerRef = useRef<HTMLDivElement>(null);

  // State management
  const [groupBy, setGroupBy] = useState<GroupByMode>('machine');
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
  const [vaultPanelVisible, setVaultPanelVisible] = useState(false);
  const [bulkAssignClusterModal, setBulkAssignClusterModal] = useState(false);
  const [removeFromClusterModal, setRemoveFromClusterModal] = useState(false);
  const [viewAssignmentStatusModal, setViewAssignmentStatusModal] = useState(false);

  // Dialog states
  const auditTrace = useTraceModal();
  const remoteFileBrowserModal = useDialogState<Machine>();
  const assignClusterModal = useDialogState<Machine>();

  // Reset to 'machine' view when entering Simple mode
  React.useEffect(() => {
    if (uiMode === 'simple' && groupBy !== 'machine') {
      setGroupBy('machine');
    }
  }, [uiMode, groupBy]);

  // Queries
  const { data: machines = [], isLoading, refetch } = useGetTeamMachines(teamFilter?.[0]);
  const { data: repositories = [] } = useGetTeamRepositories(teamFilter?.[0]);

  // Dynamic page size
  const dynamicPageSize = useDynamicPageSize(tableContainerRef, {
    containerOffset: 170,
    minRows: 5,
    maxRows: 50,
  });

  const filteredMachines = machines;

  // Parse machine vault status to get repository information
  const getMachineRepositories = useCallback(
    (machine: Machine) => {
      return coreGetMachineRepositories(
        machine,
        repositories.map((r) => ({
          repositoryGuid: r.repositoryGuid ?? '',
          repositoryName: r.repositoryName ?? '',
          grandGuid: r.grandGuid ?? '',
        }))
      );
    },
    [repositories]
  );

  const handleDelete = useCallback(
    (machine: Machine) => {
      if (onDeleteMachine) {
        onDeleteMachine(machine);
      }
    },
    [onDeleteMachine]
  );

  const handleRowClick = useCallback(
    (machine: Machine) => {
      if (onRowClick) {
        onRowClick(machine);
      } else {
        setSelectedMachine(machine);
        setVaultPanelVisible(true);
      }
    },
    [onRowClick]
  );

  const handlePanelClose = useCallback(() => {
    setVaultPanelVisible(false);
    setSelectedMachine(null);
  }, []);

  // Get machine functions
  const { getFunctionsByCategory } = useLocalizedFunctions();
  const machineFunctions = useMemo(
    () =>
      getFunctionsByCategory('machine').filter(
        (func) =>
          func &&
          func.showInMenu !== false &&
          func.name !== 'repository_mount' &&
          func.name !== 'backup_pull'
      ),
    [getFunctionsByCategory]
  ) as MachineFunctionAction[];

  const canAssignToCluster = isExpertMode && featureFlags.isEnabled('ceph');

  // Wrapper functions for column builder compatibility
  const openAssignClusterModal = useCallback(
    (state: { open: boolean; machine: Machine | null }) => {
      if (state.open && state.machine) {
        assignClusterModal.open(state.machine);
      } else {
        assignClusterModal.close();
      }
    },
    [assignClusterModal]
  );

  const openAuditTraceModal = useCallback(
    (state: {
      open: boolean;
      entityType: string | null;
      entityIdentifier: string | null;
      entityName?: string;
    }) => {
      if (state.open && state.entityType && state.entityIdentifier) {
        auditTrace.open({
          entityType: state.entityType,
          entityIdentifier: state.entityIdentifier,
          entityName: state.entityName,
        });
      } else {
        auditTrace.close();
      }
    },
    [auditTrace]
  );

  const columns = useMemo(
    () =>
      buildMachineTableColumns({
        t,
        isExpertMode,
        uiMode,
        showActions,
        hasSplitView: Boolean(onRowClick),
        canAssignToCluster,
        onEditMachine,
        onFunctionsMachine,
        handleDelete,
        handleRowClick,
        onViewRepositories: (machine) =>
          navigate(`/machines/${machine.machineName}/repositories`, { state: { machine } }),
        executePingForMachineAndWait,
        setAssignClusterModal: openAssignClusterModal,
        setAuditTraceModal: openAuditTraceModal,
        machineFunctions,
      }),
    [
      t,
      isExpertMode,
      uiMode,
      showActions,
      onRowClick,
      canAssignToCluster,
      onEditMachine,
      onFunctionsMachine,
      handleDelete,
      handleRowClick,
      navigate,
      executePingForMachineAndWait,
      openAssignClusterModal,
      openAuditTraceModal,
      machineFunctions,
    ]
  );

  // Row selection configuration
  const rowSelection = canAssignToCluster
    ? {
        selectedRowKeys,
        onChange: (newSelectedRowKeys: React.Key[]) => {
          setSelectedRowKeys(newSelectedRowKeys as string[]);
        },
        getCheckboxProps: (record: Machine) => ({
          disabled: false,
          'data-testid': `machine-checkbox-${record.machineName}`,
        }),
      }
    : undefined;

  // Grouped machines hook
  const groupedMachinesForTable = useGroupedMachines({
    machines: filteredMachines,
    groupBy,
    repositories: repositories.map((r) => ({
      repositoryGuid: r.repositoryGuid ?? '',
      repositoryName: r.repositoryName ?? '',
      grandGuid: r.grandGuid ?? '',
    })),
    getMachineRepositories,
  });

  // Mobile render
  const mobileRender = useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: Machine) => {
      const menuItems: MenuProps['items'] = [
        {
          key: 'viewRepositories',
          label: t('resources:repositories.repositories'),
          icon: <FolderOpenOutlined />,
          onClick: () =>
            navigate(`/machines/${record.machineName}/repositories`, {
              state: { machine: record },
            }),
        },
        {
          key: 'viewDetails',
          label: t('resources:audit.details'),
          icon: <EyeOutlined />,
          onClick: () => handleRowClick(record),
        },
        { type: 'divider' as const },
        ...(onEditMachine
          ? [
              {
                key: 'edit',
                label: t('common:actions.edit'),
                icon: <EditOutlined />,
                onClick: () => onEditMachine(record),
              },
            ]
          : []),
        ...(onFunctionsMachine
          ? [
              {
                key: 'functions',
                label: t('machines:functions'),
                icon: <FunctionOutlined />,
                onClick: () => onFunctionsMachine(record),
              },
            ]
          : []),
        {
          key: 'trace',
          label: t('resources:audit.trace'),
          icon: <HistoryOutlined />,
          onClick: () =>
            auditTrace.open({
              entityType: 'Machine',
              entityIdentifier: record.machineName ?? '',
              entityName: record.machineName ?? undefined,
            }),
        },
        ...(onDeleteMachine
          ? [
              { type: 'divider' as const },
              {
                key: 'delete',
                label: t('common:actions.delete'),
                icon: <DeleteOutlined />,
                danger: true,
                onClick: () => handleDelete(record),
              },
            ]
          : []),
      ];

      return (
        <MobileCard actions={<ResourceActionsDropdown menuItems={menuItems} />}>
          <Space>
            <DesktopOutlined />
            <Typography.Text strong className="truncate">
              {record.machineName}
            </Typography.Text>
          </Space>
          <Flex wrap>
            <Tag>{record.teamName}</Tag>
            {record.bridgeName && <Tag>{record.bridgeName}</Tag>}
            {record.regionName && <Tag>{record.regionName}</Tag>}
          </Flex>
        </MobileCard>
      );
    },
    [
      t,
      navigate,
      onEditMachine,
      onFunctionsMachine,
      onDeleteMachine,
      auditTrace,
      handleDelete,
      handleRowClick,
    ]
  );

  // Render grouped table view
  const renderGroupedTableView = () => {
    if (Object.keys(groupedMachinesForTable).length === 0) {
      return (
        <Flex>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('resources:repositories.noRepositories')}
          />
        </Flex>
      );
    }

    return (
      <Flex vertical>
        {Object.entries(groupedMachinesForTable).map(([groupKey, groupMachines]) => (
          <GroupedMachineCard
            key={groupKey}
            groupKey={groupKey}
            groupBy={groupBy}
            machines={groupMachines}
            columns={columns}
            mobileRender={mobileRender}
            loading={isLoading}
            pageSize={10}
            rowSelection={rowSelection}
            onRow={(record) => {
              const props: React.HTMLAttributes<HTMLElement> & Record<string, string> = {
                'data-testid': `machine-row-${record.machineName}`,
              };
              return props;
            }}
          />
        ))}
      </Flex>
    );
  };

  return (
    <Flex vertical className={`h-full ${className}`}>
      <ViewToggleButtons
        groupBy={groupBy}
        setGroupBy={setGroupBy}
        uiMode={uiMode}
        isExpertMode={isExpertMode}
        t={t}
      />
      <BulkActionsToolbar
        selectedRowKeys={selectedRowKeys}
        setSelectedRowKeys={setSelectedRowKeys}
        canAssignToCluster={canAssignToCluster}
        onAssignToCluster={() => setBulkAssignClusterModal(true)}
        onRemoveFromCluster={() => setRemoveFromClusterModal(true)}
        onViewAssignmentStatus={() => setViewAssignmentStatusModal(true)}
        t={t}
      />

      {groupBy === 'machine' ? (
        <Flex vertical ref={tableContainerRef} className="flex-1 overflow-hidden">
          <ResourceListView<Machine>
            loading={isLoading}
            data={filteredMachines}
            columns={columns}
            rowKey="machineName"
            rowSelection={rowSelection}
            mobileRender={mobileRender}
            searchPlaceholder={t('searchMachines')}
            searchTestId="machines-search-input"
            refreshTestId="machines-refresh-button"
            pagination={{
              pageSize: dynamicPageSize,
              showSizeChanger: false,
              showTotal: (total, range) =>
                t('common:table.showingRecords', { start: range[0], end: range[1], total }),
            }}
            onRow={(record) => {
              const props: React.HTMLAttributes<HTMLElement> & Record<string, string> = {
                'data-testid': `machine-row-${record.machineName}`,
              };
              return props;
            }}
          />
        </Flex>
      ) : (
        renderGroupedTableView()
      )}

      {/* Modals */}
      <AuditTraceModal
        open={auditTrace.isOpen}
        onCancel={auditTrace.close}
        entityType={auditTrace.entityType}
        entityIdentifier={auditTrace.entityIdentifier}
        entityName={auditTrace.entityName}
      />

      {remoteFileBrowserModal.state.data && (
        <RemoteFileBrowserModal
          open={remoteFileBrowserModal.isOpen}
          onCancel={remoteFileBrowserModal.close}
          machineName={remoteFileBrowserModal.state.data.machineName ?? ''}
          teamName={remoteFileBrowserModal.state.data.teamName ?? ''}
          bridgeName={remoteFileBrowserModal.state.data.bridgeName ?? ''}
          onQueueItemCreated={onQueueItemCreated}
        />
      )}

      {assignClusterModal.state.data && (
        <AssignToClusterModal
          open={assignClusterModal.isOpen}
          machine={assignClusterModal.state.data}
          onCancel={assignClusterModal.close}
          onSuccess={() => {
            assignClusterModal.close();
            void refetch();
          }}
        />
      )}

      <AssignToClusterModal
        open={bulkAssignClusterModal}
        machines={machines.filter((m) => selectedRowKeys.includes(m.machineName ?? ''))}
        onCancel={() => setBulkAssignClusterModal(false)}
        onSuccess={() => {
          setBulkAssignClusterModal(false);
          setSelectedRowKeys([]);
          void refetch();
        }}
      />

      <RemoveFromClusterModal
        open={removeFromClusterModal}
        machines={machines.filter((m) => selectedRowKeys.includes(m.machineName ?? ''))}
        onCancel={() => setRemoveFromClusterModal(false)}
        onSuccess={() => {
          setRemoveFromClusterModal(false);
          setSelectedRowKeys([]);
          void refetch();
        }}
      />

      <ViewAssignmentStatusModal
        open={viewAssignmentStatusModal}
        machines={machines.filter((m) => selectedRowKeys.includes(m.machineName ?? ''))}
        onCancel={() => setViewAssignmentStatusModal(false)}
      />

      {!onRowClick && (
        <MachineVaultStatusPanel
          machine={selectedMachine}
          visible={vaultPanelVisible}
          onClose={handlePanelClose}
        />
      )}
    </Flex>
  );
};
