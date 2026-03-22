import { Flex, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { createTruncatedColumn, RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import { SizedModal } from '@/components/common/SizedModal';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import type { Machine } from '@/types';
import { ModalSize } from '@/types/modal';
import { CloudServerOutlined, InfoCircleOutlined } from '@/utils/optimizedIcons';

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
      ? allMachines.filter((machine) => selectedMachines.includes(machine.machineName ?? ''))
      : []);
  const noneLabel = t('common:none');

  const machineColumn = createTruncatedColumn<Machine>({
    title: t('machines:machineName'),
    dataIndex: 'machineName',
    key: 'machineName',
    width: 200,
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
      width: 150,
      renderWrapper: (content) => <Tag bordered={false}>{content}</Tag>,
    }),
    responsive: RESPONSIVE_HIDE_XS,
  };

  const clusterColumn = {
    ...createTruncatedColumn<Machine>({
      title: t('ceph:clusters.cluster'),
      dataIndex: 'cephClusterName',
      key: 'cluster',
      renderText: (cluster?: string | null) => cluster ?? noneLabel,
      renderWrapper: (content, fullText) =>
        fullText === noneLabel ? (
          <Typography.Text>{fullText}</Typography.Text>
        ) : (
          <Tag bordered={false}>{content}</Tag>
        ),
    }),
    responsive: RESPONSIVE_HIDE_XS,
  };

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
    <SizedModal
      title={
        <Flex align="center" wrap>
          <InfoCircleOutlined />
          {t('machines:bulkActions.viewAssignmentStatus')}
        </Flex>
      }
      className="view-assignment-status-modal"
      size={ModalSize.Large}
      open={open}
      onCancel={onCancel}
      footer={null}
      data-testid="ds-view-assignment-status-modal"
    >
      <Flex
        align="center"
        className="gap-md"
        wrap
        // eslint-disable-next-line no-restricted-syntax
        style={{ marginBottom: 16 }}
      >
        <Flex align="center">
          <Typography.Text>{t('common:total')}:</Typography.Text>
          <Typography.Text>{totalMachines}</Typography.Text>
        </Flex>
        <Flex align="center">
          <MachineAssignmentStatusBadge assignmentType="AVAILABLE" size="small" />
          <Typography.Text>{stats.available}</Typography.Text>
        </Flex>
        <Flex align="center">
          <MachineAssignmentStatusBadge assignmentType="CLUSTER" size="small" />
          <Typography.Text>{stats.cluster}</Typography.Text>
        </Flex>
      </Flex>

      <Table<Machine>
        columns={columns}
        dataSource={targetMachines}
        rowKey="machineName"
        pagination={{
          pageSize: 10,
          showSizeChanger: false,
        }}
        scroll={{ x: 'max-content', y: 400 }}
        data-testid="ds-view-assignment-status-table"
      />
    </SizedModal>
  );
};
