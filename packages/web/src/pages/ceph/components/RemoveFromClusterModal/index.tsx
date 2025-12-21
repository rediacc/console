import React, { useState } from 'react';
import { Alert, Flex, Modal, Table, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useUpdateMachineClusterAssignment } from '@/api/queries/cephMutations';
import { createTruncatedColumn } from '@/components/common/columns';
import type { Machine } from '@/types';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import { WarningOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';

interface RemoveFromClusterModalProps {
  open: boolean;
  selectedMachines?: string[];
  allMachines?: Machine[];
  machines?: Machine[];
  onCancel: () => void;
  onSuccess?: () => void;
}

export const RemoveFromClusterModal: React.FC<RemoveFromClusterModalProps> = ({
  open,
  machines,
  selectedMachines,
  allMachines,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation(['machines', 'ceph', 'common']);
  const [removing, setRemoving] = useState(false);

  // Update mutation
  const updateMutation = useUpdateMachineClusterAssignment();

  // Determine which machines to use
  const targetMachines: Machine[] =
    machines ??
    (selectedMachines && allMachines
      ? allMachines.filter((machine) => selectedMachines.includes(machine.machineName))
      : []);

  // Filter machines that have cluster assignments
  const machinesWithClusters = targetMachines.filter((machine) => machine.cephClusterName);

  const handleOk = async () => {
    if (machinesWithClusters.length === 0) return;

    setRemoving(true);

    try {
      // Remove each machine from its cluster
      const results = await Promise.allSettled(
        machinesWithClusters.map((machine) =>
          updateMutation.mutateAsync({
            teamName: machine.teamName,
            machineName: machine.machineName,
            clusterName: '', // Empty string to remove assignment
          })
        )
      );

      // Count successes and failures
      const succeeded = results.filter((r) => r.status === 'fulfilled').length;
      const failed = results.filter((r) => r.status === 'rejected').length;

      if (failed === 0) {
        showMessage('success', t('machines:bulkOperations.removalSuccess', { count: succeeded }));
      } else {
        showMessage(
          'warning',
          t('machines:bulkOperations.assignmentPartial', {
            success: succeeded,
            total: machinesWithClusters.length,
          })
        );
      }

      if (onSuccess) onSuccess();
      onCancel();
    } catch {
      showMessage('error', t('ceph:machines.unassignError'));
    } finally {
      setRemoving(false);
    }
  };

  const noneLabel = t('common:none');

  const machineColumn = createTruncatedColumn<Machine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    renderWrapper: (content) => (
      <Flex align="center" gap={8}>
        <CloudServerOutlined />
        <Typography.Text strong style={{ fontSize: 12 }}>
          {content}
        </Typography.Text>
      </Flex>
    ),
  });

  const clusterColumn = createTruncatedColumn<Machine>({
    title: t('ceph:clusters.cluster'),
    dataIndex: 'cephClusterName',
    key: 'cluster',
    renderText: (cluster?: string | null) => cluster || noneLabel,
    renderWrapper: (content, fullText) =>
      fullText === noneLabel ? (
        <Typography.Text style={{ fontSize: 12 }}>{fullText}</Typography.Text>
      ) : (
        <Tag bordered={false} color="processing" style={{ fontSize: 12 }}>
          {content}
        </Tag>
      ),
  });

  const columns: ColumnsType<Machine> = [machineColumn, clusterColumn];

  return (
    <Modal
      title={
        <Flex align="center" gap={8} wrap>
          <WarningOutlined style={{ fontSize: 16 }} />
          {t('machines:bulkActions.removeFromCluster')}
        </Flex>
      }
      className={`${ModalSize.Medium} remove-from-cluster-modal`}
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      okText={t('common:actions.remove')}
      cancelText={t('common:actions.cancel')}
      confirmLoading={removing}
      okButtonProps={{
        danger: true,
        disabled: machinesWithClusters.length === 0,
        'data-testid': 'ds-remove-cluster-ok-button',
      }}
      cancelButtonProps={{
        'data-testid': 'ds-remove-cluster-cancel-button',
      }}
      data-testid="ds-remove-cluster-modal"
    >
      {machinesWithClusters.length === 0 ? (
        <Alert message={t('machines:noMachinesWithClusters')} type="info" showIcon />
      ) : (
        <>
          <Alert
            message={t('machines:removeFromClusterWarning', { count: machinesWithClusters.length })}
            description={t('machines:removeFromClusterDescription')}
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <Table<Machine>
            columns={columns}
            dataSource={machinesWithClusters}
            rowKey="machineName"
            size="small"
            pagination={false}
            scroll={{ y: 300 }}
            data-testid="ds-remove-cluster-table"
          />
        </>
      )}
    </Modal>
  );
};
