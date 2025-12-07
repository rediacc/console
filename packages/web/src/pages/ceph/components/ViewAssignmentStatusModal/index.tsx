import React from 'react';
import { Table } from 'antd';
import { useTranslation } from 'react-i18next';
import { createTruncatedColumn } from '@/components/common/columns';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import type { Machine } from '@/types';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import {
  StyledModal,
  TitleStack,
  InfoIcon,
  SummaryRow,
  SummaryItem,
  SummaryLabel,
  SummaryValue,
  MachinesTable,
  MachineNameRow,
  MachineNameText,
  TeamTag,
  ClusterTag,
  MutedText,
} from './styles';
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
      <MachineNameRow>
        <CloudServerOutlined />
        <MachineNameText>{content}</MachineNameText>
      </MachineNameRow>
    ),
  });

  const teamColumn = createTruncatedColumn<Machine>({
    title: t('machines:team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    renderWrapper: (content) => <TeamTag>{content}</TeamTag>,
  });

  const clusterColumn = createTruncatedColumn<Machine>({
    title: t('ceph:clusters.cluster'),
    dataIndex: 'cephClusterName',
    key: 'cluster',
    renderText: (cluster?: string | null) => cluster || noneLabel,
    renderWrapper: (content, fullText) =>
      fullText === noneLabel ? (
        <MutedText>{fullText}</MutedText>
      ) : (
        <ClusterTag>{content}</ClusterTag>
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
    <StyledModal
      title={
        <TitleStack>
          <InfoIcon />
          {t('machines:bulkActions.viewAssignmentStatus')}
        </TitleStack>
      }
      open={open}
      onCancel={onCancel}
      footer={null}
      data-testid="ds-view-assignment-status-modal"
    >
      <SummaryRow>
        <SummaryItem>
          <SummaryLabel>{t('common:total')}:</SummaryLabel>
          <SummaryValue>{totalMachines}</SummaryValue>
        </SummaryItem>
        <SummaryItem>
          <MachineAssignmentStatusBadge assignmentType="AVAILABLE" size="small" />
          <SummaryValue>{stats.available}</SummaryValue>
        </SummaryItem>
        <SummaryItem>
          <MachineAssignmentStatusBadge assignmentType="CLUSTER" size="small" />
          <SummaryValue>{stats.cluster}</SummaryValue>
        </SummaryItem>
      </SummaryRow>

      <MachinesTable
        as={Table<Machine>}
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
    </StyledModal>
  );
};
