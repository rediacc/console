import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Flex, Select, Table, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  useGetCephClusters,
  useUpdateMachineCeph,
  useUpdateMachineClusterAssignment,
} from '@/api/api-hooks.generated';
import { createTruncatedColumn, RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { SizedModal } from '@/components/common/SizedModal';
import type { Machine } from '@/types';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';

interface AssignToClusterModalProps {
  open: boolean;
  machine?: Machine | null;
  machines?: Machine[]; // For bulk operations
  onCancel: () => void;
  onSuccess?: () => void;
}

export const AssignToClusterModal: React.FC<AssignToClusterModalProps> = ({
  open,
  machine,
  machines,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation(['machines', 'ceph', 'common']);
  const isBulkMode = !!machines && machines.length > 0;

  // Determine target machines based on mode
  let targetMachines: Machine[] = [];
  if (isBulkMode) {
    targetMachines = machines;
  } else if (machine) {
    targetMachines = [machine];
  }

  const [selectedCluster, setSelectedCluster] = useState<string | null>(
    machine?.cephClusterName ?? null
  );

  // Load clusters for the machine's team(s)
  const { data: clusters = [], isLoading: clustersLoading } = useGetCephClusters();

  // Update mutations
  const updateMutation = useUpdateMachineCeph();
  const updateClusterMutation = useUpdateMachineClusterAssignment();

  const handleOk = async () => {
    if (!selectedCluster || targetMachines.length === 0) return;

    try {
      if (isBulkMode) {
        // Bulk assignment
        const results = await Promise.allSettled(
          targetMachines.map((m) =>
            updateClusterMutation.mutateAsync({
              teamName: m.teamName,
              machineName: m.machineName,
              clusterName: selectedCluster,
            })
          )
        );

        const succeeded = results.filter((r) => r.status === 'fulfilled').length;
        const failed = results.filter((r) => r.status === 'rejected').length;

        if (failed === 0) {
          showMessage(
            'success',
            t('machines:bulkOperations.assignmentSuccess', { count: succeeded })
          );
        } else {
          showMessage(
            'warning',
            t('machines:bulkOperations.assignmentPartial', {
              success: succeeded,
              total: targetMachines.length,
            })
          );
        }
      } else {
        // Single assignment
        await updateMutation.mutateAsync({
          teamName: machine!.teamName,
          machineName: machine!.machineName,
          clusterName: selectedCluster,
        });

        showMessage(
          'success',
          selectedCluster
            ? t('machines:clusterAssignedSuccess', { cluster: selectedCluster })
            : t('machines:clusterUnassignedSuccess')
        );
      }

      onSuccess?.();
      onCancel();
    } catch {
      // Error is handled by the mutation
    }
  };

  // Reset selected cluster when modal opens with different machine
  useEffect(() => {
    if (open && machine && !isBulkMode) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedCluster(machine.cephClusterName ?? null);
    } else if (open && isBulkMode) {
      setSelectedCluster(null);
    }
  }, [open, machine, isBulkMode]);

  const bulkColumns: ColumnsType<Machine> = useMemo(() => {
    const machineColumn = createTruncatedColumn<Machine>({
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      renderWrapper: (content) => (
        <Flex align="center">
          <CloudServerOutlined />
          <Typography.Text>{content}</Typography.Text>
        </Flex>
      ),
    });

    const teamColumn = {
      ...createTruncatedColumn<Machine>({
        title: t('machines:team'),
        dataIndex: 'teamName',
        key: 'teamName',
        renderWrapper: (content) => <Tag bordered={false}>{content}</Tag>,
      }),
      responsive: RESPONSIVE_HIDE_XS,
    };

    return [
      machineColumn,
      teamColumn,
      {
        title: t('machines:assignmentStatus.title'),
        key: 'currentCluster',
        render: (_: unknown, record: Machine) =>
          record.cephClusterName ? (
            <Tag bordered={false}>{record.cephClusterName}</Tag>
          ) : (
            <Tag bordered={false}>{t('machines:assignmentStatus.available')}</Tag>
          ),
      },
    ];
  }, [t]);

  const clusterOptions = useMemo(
    () =>
      clusters.map((cluster) => ({
        value: cluster.clusterName,
        label: cluster.clusterName,
      })),
    [clusters]
  );

  return (
    <SizedModal
      className="assign-to-cluster-modal"
      size={isBulkMode ? ModalSize.Large : ModalSize.Medium}
      title={
        <Flex align="center" wrap>
          <CloudServerOutlined />
          {(() => {
            if (isBulkMode) {
              return t('machines:bulkActions.assignToCluster');
            } else if (machine?.cephClusterName) {
              return t('machines:changeClusterAssignment');
            }
            return t('machines:assignToCluster');
          })()}
        </Flex>
      }
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={updateMutation.isPending || updateClusterMutation.isPending}
      okText={t('common:actions.save')}
      cancelText={t('common:actions.cancel')}
      okButtonProps={{
        disabled: !selectedCluster,
        'data-testid': 'ds-assign-cluster-ok-button',
      }}
      cancelButtonProps={{
        'data-testid': 'ds-assign-cluster-cancel-button',
      }}
      data-testid="ds-assign-cluster-modal"
    >
      <Flex vertical className="w-full">
        {isBulkMode ? (
          <>
            <Alert
              message={t('machines:bulkOperations.selectedCount', { count: targetMachines.length })}
              description={t('machines:bulkAssignDescription')}
              type="info"
            />
            <Table<Machine>
              columns={bulkColumns}
              dataSource={targetMachines}
              rowKey="machineName"
              pagination={false}
              scroll={{ x: 'max-content', y: 200 }}
              data-testid="ds-assign-cluster-bulk-table"
            />
          </>
        ) : (
          machine && (
            <>
              <Flex vertical className="gap-2">
                <Flex align="flex-start" wrap>
                  <Typography.Text strong>{t('machines:machine')}:</Typography.Text>
                  <Typography.Text>{machine.machineName}</Typography.Text>
                </Flex>
                <Flex align="flex-start" wrap>
                  <Typography.Text strong>{t('machines:team')}:</Typography.Text>
                  <Typography.Text>{machine.teamName}</Typography.Text>
                </Flex>
              </Flex>

              {machine.cephClusterName && (
                <Alert
                  message={t('machines:currentClusterAssignment', {
                    cluster: machine.cephClusterName,
                  })}
                  type="info"
                />
              )}
            </>
          )
        )}

        <Flex vertical className="w-full gap-2">
          <Typography.Text>{t('ceph:clusters.cluster')}:</Typography.Text>
          {clustersLoading ? (
            <LoadingWrapper loading centered minHeight={80}>
              <Flex />
            </LoadingWrapper>
          ) : (
            <>
              <Select
                placeholder={t('machines:selectCluster')}
                value={selectedCluster}
                onChange={(value) => setSelectedCluster(value as string | null)}
                showSearch
                optionFilterProp="children"
                options={clusterOptions}
                className="w-full"
                data-testid="ds-assign-cluster-select"
              />
              {!isBulkMode && (
                <Typography.Text>{t('machines:clusterAssignmentHelp')}</Typography.Text>
              )}
            </>
          )}
        </Flex>
      </Flex>
    </SizedModal>
  );
};
