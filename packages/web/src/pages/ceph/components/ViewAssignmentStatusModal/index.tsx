import React from 'react';
import { Flex, Modal, Table, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { createTruncatedColumn } from '@/components/common/columns';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import type { Machine } from '@/types';
import { ModalSize } from '@/types/modal';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import { InfoCircleOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';

interface ViewAssignmentStatusModalProps {
  open: boolean;
  selectedMachines?: string[];
  allMachines?: Machine[];
  machines?: Machine[];
  onCancel: () => void;
}

export const ViewAssignmentStatusModal: React.FC<ViewAssignmentStatusModalProps> = ({
  open,
  machines,
  selectedMachines,
  allMachines,
  onCancel,
}) => {
  const { t } = useTranslation(['machines', 'ceph', 'common']);

  // Determine which machines to use
  const targetMachines: Machine[] =
    machines ??
    (selectedMachines && allMachines
      ? allMachines.filter((machine) => selectedMachines.includes(machine.machineName))
      : []);
  const noneLabel = t('common:none');

  const machineColumn = createTruncatedColumn<Machine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    width: 200,
    renderWrapper: (content) => (
      <Flex align="center" gap={8}>
        <CloudServerOutlined />
        <Typography.Text strong style={{ fontSize: 12 }}>
          {content}
        </Typography.Text>
      </Flex>
    ),
  });

  const teamColumn = createTruncatedColumn<Machine>({
    title: t('machines:team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    renderWrapper: (content) => (
      <Tag bordered={false} color="success" style={{ fontSize: 12 }}>
        {content}
      </Tag>
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

  const columns: ColumnsType<Machine> = [
    machineColumn,
    teamColumn,
    {
      title: t('machines:assignmentStatus.title'),
      key: 'assignmentStatus',
      width: 200,
      render: (_: unknown, record: Machine) => <MachineAssignmentStatusCell machine={record} />,
    },
    clusterColumn,
  ];

  // Calculate summary statistics
  const stats = targetMachines.reduce(
    (acc, machine) => {
      if (machine.cephClusterName) {
        acc.cluster += 1;
      } else {
        acc.available += 1;
      }
      return acc;
    },
    { available: 0, cluster: 0 }
  );
  const totalMachines = targetMachines.length;

  return (
    <Modal
      title={
        <Flex align="center" gap={8} wrap>
          <InfoCircleOutlined />
          {t('machines:bulkActions.viewAssignmentStatus')}
        </Flex>
      }
      className={`${ModalSize.Large} view-assignment-status-modal`}
      open={open}
      onCancel={onCancel}
      footer={null}
      data-testid="ds-view-assignment-status-modal"
    >
      <Flex align="center" gap={16} wrap style={{ marginBottom: 16 }}>
        <Flex align="center" gap={8}>
          <Typography.Text style={{ fontSize: 12 }}>{t('common:total')}:</Typography.Text>
          <Typography.Text strong>{totalMachines}</Typography.Text>
        </Flex>
        <Flex align="center" gap={8}>
          <MachineAssignmentStatusBadge assignmentType="AVAILABLE" size="small" />
          <Typography.Text strong>{stats.available}</Typography.Text>
        </Flex>
        <Flex align="center" gap={8}>
          <MachineAssignmentStatusBadge assignmentType="CLUSTER" size="small" />
          <Typography.Text strong>{stats.cluster}</Typography.Text>
        </Flex>
      </Flex>

      <Table<Machine>
        columns={columns}
        dataSource={targetMachines}
        rowKey="machineName"
        size="small"
        pagination={{
          pageSize: 10,
          showSizeChanger: false,
        }}
        scroll={{ y: 400 }}
        data-testid="ds-view-assignment-status-table"
      />
    </Modal>
  );
};
