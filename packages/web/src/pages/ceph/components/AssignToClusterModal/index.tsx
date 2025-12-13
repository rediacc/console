import React, { useEffect, useMemo, useState } from 'react';
import { Table } from 'antd';
import { useTranslation } from 'react-i18next';
import { type CephCluster, useCephClusters } from '@/api/queries/ceph';
import {
  useUpdateMachineCeph,
  useUpdateMachineClusterAssignment,
} from '@/api/queries/cephMutations';
import { createTruncatedColumn } from '@/components/common/columns';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccStack, RediaccText } from '@/components/ui';
import { AlertCard } from '@/styles/primitives';
import type { Machine } from '@/types';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import {
  AssignmentTag,
  ClusterAlert,
  DetailRow,
  FieldGroup,
  MachineDetailsSection,
  MachineNameRow,
  MachinesTable,
  StyledModal,
  StyledSelect,
  TeamTag,
  TitleStack,
} from './styles';
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
  const targetMachines: Machine[] = isBulkMode && machines ? machines : machine ? [machine] : [];

  const [selectedCluster, setSelectedCluster] = useState<string | null>(
    machine?.cephClusterName || null
  );

  // Get unique teams from all machines for bulk mode
  const uniqueTeams: string[] =
    isBulkMode && machines
      ? Array.from(new Set(machines.map((m) => m.teamName)))
      : machine
        ? [machine.teamName]
        : [];

  // Load clusters for the machine's team(s)
  const { data: clusters = [], isLoading: clustersLoading } = useCephClusters(
    uniqueTeams,
    open && uniqueTeams.length > 0
  ) as { data: CephCluster[]; isLoading: boolean };

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
      setSelectedCluster(machine.cephClusterName || null);
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
        <MachineNameRow>
          <CloudServerOutlined />
          <RediaccText weight="medium">{content}</RediaccText>
        </MachineNameRow>
      ),
    });

    const teamColumn = createTruncatedColumn<Machine>({
      title: t('machines:team'),
      dataIndex: 'teamName',
      key: 'teamName',
      renderWrapper: (content) => <TeamTag>{content}</TeamTag>,
    });

    return [
      machineColumn,
      teamColumn,
      {
        title: t('machines:assignmentStatus.title'),
        key: 'currentCluster',
        render: (_: unknown, record: Machine) =>
          record.cephClusterName ? (
            <AssignmentTag variant="primary">{record.cephClusterName}</AssignmentTag>
          ) : (
            <AssignmentTag variant="success">
              {t('machines:assignmentStatus.available')}
            </AssignmentTag>
          ),
      },
    ];
  }, [t]);

  const modalSize = isBulkMode ? ModalSize.Large : ModalSize.Medium;

  const clusterOptions = useMemo(
    () =>
      clusters.map((cluster) => ({
        value: cluster.clusterName,
        label: cluster.clusterName,
      })),
    [clusters]
  );

  return (
    <StyledModal
      $size={modalSize}
      title={
        <TitleStack>
          <CloudServerOutlined />
          {isBulkMode
            ? t('machines:bulkActions.assignToCluster')
            : machine?.cephClusterName
              ? t('machines:changeClusterAssignment')
              : t('machines:assignToCluster')}
        </TitleStack>
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
      <RediaccStack variant="spaced-column" fullWidth>
        {isBulkMode ? (
          <>
            <AlertCard
              $variant="info"
              message={t('machines:bulkOperations.selectedCount', { count: targetMachines.length })}
              description={t('machines:bulkAssignDescription')}
              variant="info"
              showIcon
            />
            <MachinesTable
              as={Table<Machine>}
              columns={bulkColumns}
              dataSource={targetMachines}
              rowKey="machineName"
              size="small"
              pagination={false}
              scroll={{ y: 200 }}
              data-testid="ds-assign-cluster-bulk-table"
            />
          </>
        ) : (
          machine && (
            <>
              <MachineDetailsSection>
                <DetailRow>
                  <RediaccText weight="semibold">{t('machines:machine')}:</RediaccText>
                  <RediaccText color="muted">{machine.machineName}</RediaccText>
                </DetailRow>
                <DetailRow>
                  <RediaccText weight="semibold">{t('machines:team')}:</RediaccText>
                  <RediaccText color="muted">{machine.teamName}</RediaccText>
                </DetailRow>
              </MachineDetailsSection>

              {machine.cephClusterName && (
                <ClusterAlert
                  message={t('machines:currentClusterAssignment', {
                    cluster: machine.cephClusterName,
                  })}
                  variant="info"
                  showIcon
                />
              )}
            </>
          )
        )}

        <FieldGroup>
          <RediaccText weight="medium" size="sm">
            {t('ceph:clusters.cluster')}:
          </RediaccText>
          {clustersLoading ? (
            <LoadingWrapper loading centered minHeight={80}>
              <div />
            </LoadingWrapper>
          ) : (
            <>
              <StyledSelect
                fullWidth
                placeholder={t('machines:selectCluster')}
                value={selectedCluster}
                onChange={(value) => setSelectedCluster(value as string | null)}
                showSearch
                optionFilterProp="children"
                options={clusterOptions}
                data-testid="ds-assign-cluster-select"
              />
              {!isBulkMode && (
                <RediaccText size="xs" color="muted">
                  {t('machines:clusterAssignmentHelp')}
                </RediaccText>
              )}
            </>
          )}
        </FieldGroup>
      </RediaccStack>
    </StyledModal>
  );
};
