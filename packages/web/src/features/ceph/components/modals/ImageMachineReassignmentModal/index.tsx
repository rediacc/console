import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Flex, Select, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  type AvailableMachine,
  type CephRbdImage,
  useAvailableMachinesForClone,
} from '@/api/queries/ceph';
import { useUpdateImageMachineAssignment } from '@/api/queries/cephMutations';
import { SizedModal } from '@/components/common';
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
          <Typography.Text>
            {image.machineName} ({t('common:current')})
          </Typography.Text>
        ),
        disabled: true,
      });
    }

    // Available machines
    availableMachines.forEach((machine) => {
      options.push({
        value: machine.machineName,
        label: <Typography.Text>{machine.machineName}</Typography.Text>,
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
    <SizedModal
      title={
        <Flex align="center" gap={8} wrap className="inline-flex">
          <FileImageOutlined />
          {t('ceph:images.reassignMachine')}
        </Flex>
      }
      className="image-machine-reassignment-modal"
      size={ModalSize.Medium}
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
        <Flex vertical gap={24} className="w-full">
          <Flex align="flex-start" wrap gap={8}>
            <Typography.Text strong>{t('ceph:images.image')}:</Typography.Text>
            <Typography.Text>{image.imageName}</Typography.Text>
          </Flex>

          <Flex align="flex-start" wrap gap={8}>
            <Typography.Text strong>{t('ceph:pools.pool')}:</Typography.Text>
            <Typography.Text>{poolName}</Typography.Text>
          </Flex>

          {image.machineName && (
            <Alert
              message={t('machines:currentMachineAssignment', { machine: image.machineName })}
              type="info"
              icon={<CloudServerOutlined />}
              data-testid="image-reassign-current-machine-info"
              showIcon
            />
          )}

          <Flex vertical>
            <Typography.Text>{t('ceph:images.selectNewMachine')}:</Typography.Text>
            <Flex vertical>
              <LoadingWrapper loading={loadingMachines} centered minHeight={120}>
                <>
                  <Select
                    placeholder={t('machines:selectMachine')}
                    value={selectedMachine}
                    onChange={(value) => setSelectedMachine(value)}
                    showSearch
                    optionFilterProp="children"
                    className="w-full"
                    notFoundContent={
                      availableMachines.length === 0 ? (
                        <Typography.Text>{t('machines:noAvailableMachines')}</Typography.Text>
                      ) : (
                        <Typography.Text>{t('common:noMatchingResults')}</Typography.Text>
                      )
                    }
                    options={selectOptions}
                    data-testid="image-reassign-machine-select"
                  />

                  <Typography.Text>{t('ceph:images.reassignmentInfo')}</Typography.Text>
                </>
              </LoadingWrapper>
            </Flex>
          </Flex>

          <Alert
            message={<Typography.Text type="warning">{t('common:important')}</Typography.Text>}
            description={<Typography.Text>{t('ceph:images.reassignmentWarning')}</Typography.Text>}
            type="warning"
            showIcon
            data-testid="image-reassign-warning"
          />
        </Flex>
      )}
    </SizedModal>
  );
};
