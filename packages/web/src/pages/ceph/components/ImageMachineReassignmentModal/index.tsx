import { Alert, Flex, Modal, Select, Typography } from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  type AvailableMachine,
  type CephRbdImage,
  useAvailableMachinesForClone,
} from '@/api/queries/ceph';
import { useUpdateImageMachineAssignment } from '@/api/queries/cephMutations';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { ModalSize } from '@/types/modal';
import { CloudServerOutlined, FileImageOutlined } from '@/utils/optimizedIcons';

interface ImageMachineReassignmentModalProps {
  open: boolean;
  image: CephRbdImage | null;
  teamName: string;
  poolName: string;
  onCancel: () => void;
  onSuccess?: () => void;
}

export const ImageMachineReassignmentModal: React.FC<ImageMachineReassignmentModalProps> = ({
  open,
  image,
  teamName,
  poolName,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation(['ceph', 'machines', 'common']);
  const [selectedMachine, setSelectedMachine] = useState<string>('');
  const updateMachineAssignment = useUpdateImageMachineAssignment();

  // Fetch available machines
  const { data: availableMachines = [], isLoading: loadingMachines } = useAvailableMachinesForClone(
    teamName,
    open && !!image
  ) as { data?: AvailableMachine[]; isLoading: boolean };

  useEffect(() => {
    if (!open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedMachine('');
    }
  }, [open]);

  const selectOptions = useMemo(() => {
    const options = [];

    // Include current machine if it exists
    if (image?.machineName) {
      options.push({
        value: image.machineName,
        label: (
          <span style={{ fontSize: 14, cursor: 'not-allowed' }}>
            {image.machineName} ({t('common:current')})
          </span>
        ),
        disabled: true,
      });
    }

    // Available machines
    availableMachines.forEach((machine) => {
      options.push({
        value: machine.machineName,
        label: <span style={{ fontSize: 14 }}>{machine.machineName}</span>,
      });
    });

    return options;
  }, [image, availableMachines, t]);

  const handleOk = async () => {
    if (!image || !selectedMachine) return;

    try {
      await updateMachineAssignment.mutateAsync({
        teamName,
        poolName,
        imageName: image.imageName,
        newMachineName: selectedMachine,
      });

      if (onSuccess) onSuccess();
      onCancel();
    } catch {
      // Error is handled by the mutation hook
    }
  };

  return (
    <Modal
      title={
        <Flex align="center" gap={8} wrap style={{ display: 'inline-flex' }}>
          <FileImageOutlined style={{ fontSize: 16, color: 'var(--ant-color-primary)' }} />
          {t('ceph:images.reassignMachine')}
        </Flex>
      }
      className={`${ModalSize.Medium} image-machine-reassignment-modal`}
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      okText={t('common:actions.save')}
      cancelText={t('common:actions.cancel')}
      confirmLoading={updateMachineAssignment.isPending}
      okButtonProps={{
        disabled: !selectedMachine || selectedMachine === image?.machineName,
        'data-testid': 'image-reassign-submit',
      }}
      cancelButtonProps={{
        'data-testid': 'image-reassign-cancel',
      }}
      data-testid="image-reassign-modal"
    >
      {image && (
        <Flex vertical gap={24} style={{ width: '100%' }}>
          <Flex align="flex-start" wrap gap={8}>
            <Typography.Text strong>
              {t('ceph:images.image')}:
            </Typography.Text>
            <Typography.Text type="secondary">{image.imageName}</Typography.Text>
          </Flex>

          <Flex align="flex-start" wrap gap={8}>
            <Typography.Text strong>
              {t('ceph:pools.pool')}:
            </Typography.Text>
            <Typography.Text type="secondary">{poolName}</Typography.Text>
          </Flex>

          {image.machineName && (
            <Alert
              message={t('machines:currentMachineAssignment', { machine: image.machineName })}
              type="info"
              icon={<CloudServerOutlined style={{ fontSize: 14, color: 'var(--ant-color-primary)' }} />}
              data-testid="image-reassign-current-machine-info"
              showIcon
            />
          )}

          <div>
            <Typography.Text>
              {t('ceph:images.selectNewMachine')}:
            </Typography.Text>
            <div>
              <LoadingWrapper loading={loadingMachines} centered minHeight={120}>
                <>
                  <Select
                    placeholder={t('machines:selectMachine')}
                    value={selectedMachine}
                    onChange={(value) => setSelectedMachine(value as string)}
                    showSearch
                    optionFilterProp="children"
                    style={{ width: '100%' }}
                    notFoundContent={
                      availableMachines.length === 0 ? (
                        <span style={{ fontSize: 14 }}>{t('machines:noAvailableMachines')}</span>
                      ) : (
                        <span style={{ fontSize: 14 }}>{t('common:noMatchingResults')}</span>
                      )
                    }
                    options={selectOptions}
                    data-testid="image-reassign-machine-select"
                  />

                  <Typography.Text type="secondary">{t('ceph:images.reassignmentInfo')}</Typography.Text>
                </>
              </LoadingWrapper>
            </div>
          </div>

          <Alert
            message={<Typography.Text type="warning">{t('common:important')}</Typography.Text>}
            description={<Typography.Text>{t('ceph:images.reassignmentWarning')}</Typography.Text>}
            type="warning"
            showIcon
            data-testid="image-reassign-warning"
          />
        </Flex>
      )}
    </Modal>
  );
};
