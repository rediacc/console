import React, { useEffect, useState } from 'react';
import { Select } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  useAvailableMachinesForClone,
  type CephRbdImage,
  type AvailableMachine,
} from '@/api/queries/ceph';
import { useUpdateImageMachineAssignment } from '@/api/queries/cephMutations';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { RediaccText, RediaccStack } from '@/components/ui';
import { AlertCard } from '@/styles/primitives';
import {
  StyledModal,
  TitleStack,
  TitleIcon,
  FieldRow,
  MachineIcon,
  StyledSelect,
  SelectOptionText,
  DisabledOptionText,
  LoadingContainer,
} from './styles';

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
    <StyledModal
      title={
        <TitleStack>
          <TitleIcon />
          {t('ceph:images.reassignMachine')}
        </TitleStack>
      }
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
        <RediaccStack variant="spaced-column" fullWidth>
          <FieldRow>
            <RediaccText weight="semibold" size="sm">
              {t('ceph:images.image')}:
            </RediaccText>
            <RediaccText color="muted">{image.imageName}</RediaccText>
          </FieldRow>

          <FieldRow>
            <RediaccText weight="semibold" size="sm">
              {t('ceph:pools.pool')}:
            </RediaccText>
            <RediaccText color="muted">{poolName}</RediaccText>
          </FieldRow>

          {image.machineName && (
            <AlertCard
              $variant="info"
              message={t('machines:currentMachineAssignment', { machine: image.machineName })}
              variant="info"
              icon={<MachineIcon />}
              data-testid="image-reassign-current-machine-info"
            />
          )}

          <div>
            <RediaccText as="label" weight="medium" size="sm">
              {t('ceph:images.selectNewMachine')}:
            </RediaccText>
            <LoadingContainer>
              <LoadingWrapper loading={loadingMachines} centered minHeight={120}>
                <>
                  <StyledSelect
                    fullWidth
                    placeholder={t('machines:selectMachine')}
                    value={selectedMachine}
                    onChange={(value) => setSelectedMachine(value as string)}
                    showSearch
                    optionFilterProp="children"
                    notFoundContent={
                      availableMachines.length === 0 ? (
                        <SelectOptionText>{t('machines:noAvailableMachines')}</SelectOptionText>
                      ) : (
                        <SelectOptionText>{t('common:noMatchingResults')}</SelectOptionText>
                      )
                    }
                    data-testid="image-reassign-machine-select"
                  >
                    {/* Include current machine if it exists */}
                    {image.machineName && (
                      <Select.Option
                        key={image.machineName}
                        value={image.machineName}
                        disabled
                        data-testid={`image-reassign-machine-option-${image.machineName}`}
                      >
                        <DisabledOptionText>
                          {image.machineName} ({t('common:current')})
                        </DisabledOptionText>
                      </Select.Option>
                    )}

                    {/* Available machines */}
                    {availableMachines.map((machine) => (
                      <Select.Option
                        key={machine.machineName}
                        value={machine.machineName}
                        data-testid={`image-reassign-machine-option-${machine.machineName}`}
                      >
                        <SelectOptionText>{machine.machineName}</SelectOptionText>
                      </Select.Option>
                    ))}
                  </StyledSelect>

                  <RediaccText variant="caption">{t('ceph:images.reassignmentInfo')}</RediaccText>
                </>
              </LoadingWrapper>
            </LoadingContainer>
          </div>

          <AlertCard
            $variant="warning"
            message={<RediaccText>{t('common:important')}</RediaccText>}
            description={<RediaccText>{t('ceph:images.reassignmentWarning')}</RediaccText>}
            variant="warning"
            showIcon
            data-testid="image-reassign-warning"
          />
        </RediaccStack>
      )}
    </StyledModal>
  );
};
