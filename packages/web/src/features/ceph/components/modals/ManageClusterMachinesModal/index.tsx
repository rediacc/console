import React, { useState } from 'react';
import { Button, Empty, Flex, Modal, Space, Table, Tabs, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  useGetAvailableMachinesForClone,
  useGetCephClusterMachines,
  useUpdateMachineClusterAssignment,
  useUpdateMachineClusterRemoval,
} from '@/api/api-hooks.generated';
import {
  createDateColumn,
  createTruncatedColumn,
  RESPONSIVE_HIDE_XS,
} from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { SizedModal } from '@/components/common/SizedModal';
import { AvailableMachinesSelector } from '@/components/resources/AvailableMachinesSelector';
import { useMessage } from '@/hooks';
import { createSorter, formatTimestampAsIs } from '@/platform';
import type { Machine } from '@/types';
import { ModalSize } from '@/types/modal';
import { confirmAction } from '@/utils/confirmations';
import {
  CloudServerOutlined,
  DeleteOutlined,
  DesktopOutlined,
  PlusOutlined,
} from '@/utils/optimizedIcons';
import type { GetCephClusterMachines_ResultSet1 as CephClusterMachine } from '@rediacc/shared/types';
import type { ColumnsType } from 'antd/es/table';

interface ManageClusterMachinesModalProps {
  open: boolean;
  clusterName: string;
  teamName: string;
  onCancel: () => void;
  onSuccess?: () => void;
}

export const ManageClusterMachinesModal: React.FC<ManageClusterMachinesModalProps> = ({
  open,
  clusterName,
  teamName,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation(['ceph', 'machines', 'common']);
  const message = useMessage();
  const [confirmModal, confirmContextHolder] = Modal.useModal();
  const [activeTab, setActiveTab] = useState<'assign' | 'manage'>('assign');
  const [selectedMachines, setSelectedMachines] = useState<string[]>([]);
  const [selectedRemoveMachines, setSelectedRemoveMachines] = useState<string[]>([]);
  const [assigningMachines, setAssigningMachines] = useState(false);
  const [removingMachines, setRemovingMachines] = useState(false);

  // Fetch cluster machines
  const {
    data: clusterMachines = [],
    isLoading: loadingClusterMachines,
    refetch: refetchClusterMachines,
  } = useGetCephClusterMachines(clusterName);

  // Fetch available machines
  const { data: availableMachines = [], isLoading: loadingAvailable } =
    useGetAvailableMachinesForClone(teamName);
  const normalizedAvailableMachines = availableMachines as unknown as Machine[];

  // Mutations
  const assignMachine = useUpdateMachineClusterAssignment();
  const removeMachine = useUpdateMachineClusterRemoval();

  // Reset state when modal closes
  React.useEffect(() => {
    if (!open) {
      setActiveTab('assign');
      setSelectedMachines([]);
      setSelectedRemoveMachines([]);
    }
  }, [open]);

  const handleAssignMachines = async () => {
    if (selectedMachines.length === 0) {
      message.warning('machines:bulkOperations.selectMachines');
      return;
    }

    setAssigningMachines(true);

    try {
      // Assign each machine to the cluster
      const results = await Promise.allSettled(
        selectedMachines.map((machineName) =>
          assignMachine.mutateAsync({
            teamName,
            machineName,
            clusterName,
          })
        )
      );

      const successCount = results.filter((r) => r.status === 'fulfilled').length;
      const failedCount = results.filter((r) => r.status === 'rejected').length;

      if (failedCount === 0) {
        message.success('machines:bulkOperations.assignmentSuccess', { count: successCount });
        setSelectedMachines([]);
        void refetchClusterMachines();
        if (onSuccess) onSuccess();
      } else {
        message.warning('machines:bulkOperations.assignmentPartial', {
          success: successCount,
          total: results.length,
        });
        void refetchClusterMachines();
      }
    } finally {
      setAssigningMachines(false);
    }
  };

  const handleRemoveMachines = () => {
    if (selectedRemoveMachines.length === 0) {
      message.warning('machines:validation.noMachinesSelected');
      return;
    }

    confirmAction({
      modal: confirmModal,
      title: t('machines:removeFromCluster'),
      content: t('machines:removeFromClusterWarning', {
        count: selectedRemoveMachines.length,
      }),
      okText: t('common:actions.remove'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onConfirm: async () => {
        setRemovingMachines(true);

        try {
          const results = await Promise.allSettled(
            selectedRemoveMachines.map((machineName) =>
              removeMachine.mutateAsync({
                teamName,
                machineName,
              })
            )
          );

          const successCount = results.filter((r) => r.status === 'fulfilled').length;

          if (successCount === selectedRemoveMachines.length) {
            message.success('machines:bulkOperations.removalSuccess', { count: successCount });
            setSelectedRemoveMachines([]);
            void refetchClusterMachines();
            if (onSuccess) onSuccess();
          } else {
            message.warning('machines:bulkOperations.assignmentPartial', {
              success: successCount,
              total: results.length,
            });
            void refetchClusterMachines();
          }
        } finally {
          setRemovingMachines(false);
        }
      },
    });
  };

  // Columns for assigned machines table
  const machineColumn = createTruncatedColumn<CephClusterMachine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    sorter: createSorter<CephClusterMachine>('machineName'),
    renderWrapper: (content) => (
      <Space>
        <DesktopOutlined />
        <strong>{content}</strong>
      </Space>
    ),
  });

  const bridgeColumn = createTruncatedColumn<CephClusterMachine>({
    title: t('machines:bridge'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    sorter: createSorter<CephClusterMachine>('bridgeName'),
    renderWrapper: (content) => <Tag>{content}</Tag>,
  });

  const assignedDateColumn = {
    ...createDateColumn<CephClusterMachine>({
      title: t('machines:assignedDate'),
      dataIndex: 'assignedDate',
      key: 'assignedDate',
      sorter: false,
      render: (date: string | Date | null | undefined) => {
        if (!date) return '-';
        const resolved = typeof date === 'string' ? date : date.toString();
        return formatTimestampAsIs(resolved, 'datetime');
      },
    }),
    responsive: RESPONSIVE_HIDE_XS,
  };

  const assignedColumns: ColumnsType<CephClusterMachine> = [
    machineColumn,
    bridgeColumn,
    assignedDateColumn,
  ];

  const renderAssignTab = () => {
    if (loadingAvailable) {
      return (
        <LoadingWrapper loading centered minHeight={160}>
          <Flex />
        </LoadingWrapper>
      );
    }

    return (
      <Space direction="vertical" size="large" className="w-full">
        <Flex vertical>
          <Typography.Text>{t('machines:selectMachines')}</Typography.Text>
          <AvailableMachinesSelector
            machines={normalizedAvailableMachines}
            value={selectedMachines}
            onChange={setSelectedMachines}
          />
        </Flex>

        {selectedMachines.length > 0 && (
          <Flex>
            <Tag>
              {t('machines:bulkOperations.selectedCount', { count: selectedMachines.length })}
            </Tag>
          </Flex>
        )}
      </Space>
    );
  };

  const renderManageTab = () => {
    if (loadingClusterMachines) {
      return (
        <LoadingWrapper loading centered minHeight={160}>
          <Flex />
        </LoadingWrapper>
      );
    }

    if (clusterMachines.length === 0) {
      return <Empty description={t('clusters.noMachinesAssigned')} />;
    }

    const rowSelection = {
      selectedRowKeys: selectedRemoveMachines,
      onChange: (selectedRowKeys: React.Key[]) => {
        setSelectedRemoveMachines(selectedRowKeys as string[]);
      },
    };

    return (
      <Space direction="vertical" size="large" className="w-full">
        {selectedRemoveMachines.length > 0 && (
          <Flex>
            <Tag>
              {t('machines:bulkOperations.selectedCount', { count: selectedRemoveMachines.length })}
            </Tag>
            <Button
              type="primary"
              danger
              icon={<DeleteOutlined />}
              onClick={handleRemoveMachines}
              loading={removingMachines}
              data-testid="ds-manage-machines-remove-button"
            >
              {t('machines:removeFromCluster')}
            </Button>
          </Flex>
        )}

        <Table<CephClusterMachine>
          rowSelection={rowSelection}
          columns={assignedColumns}
          dataSource={clusterMachines}
          rowKey="machineName"
          pagination={false}
          scroll={{ x: 'max-content' }}
          data-testid="ds-manage-machines-assigned-table"
        />
      </Space>
    );
  };

  return (
    <SizedModal
      title={
        <Space>
          <CloudServerOutlined />
          {t('clusters.assignedMachines')}: {clusterName}
        </Space>
      }
      open={open}
      onCancel={onCancel}
      size={ModalSize.Large}
      data-testid="ds-manage-cluster-machines-modal"
      footer={[
        <Button key="cancel" onClick={onCancel} data-testid="ds-manage-machines-cancel">
          {t('common:actions.cancel')}
        </Button>,
        activeTab === 'assign' && (
          <Button
            key="assign"
            type="primary"
            icon={<PlusOutlined />}
            loading={assigningMachines}
            disabled={selectedMachines.length === 0}
            onClick={handleAssignMachines}
            data-testid="ds-manage-machines-assign-button"
          >
            {t('machines:assignToCluster')}
          </Button>
        ),
      ].filter(Boolean)}
    >
      {confirmContextHolder}
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as 'assign' | 'manage')}
        data-testid="ds-manage-machines-tabs"
        items={[
          {
            key: 'assign',
            label: (
              <Typography.Text data-testid="ds-manage-machines-tab-assign">
                {t('machines:assignToCluster')}
              </Typography.Text>
            ),
            children: renderAssignTab(),
          },
          {
            key: 'manage',
            label: (
              <Typography.Text data-testid="ds-manage-machines-tab-manage">
                {t('clusters.assignedMachines')}
              </Typography.Text>
            ),
            children: renderManageTab(),
          },
        ]}
      />
    </SizedModal>
  );
};
