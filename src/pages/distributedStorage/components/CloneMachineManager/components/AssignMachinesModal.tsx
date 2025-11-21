import React from 'react'
import { Modal, Alert, Spin, Empty } from 'antd'
import type { TFunction } from 'i18next'
import type { AvailableMachine } from '@/api/queries/distributedStorage'
import type { Machine } from '@/types'
import { ModalSize } from '@/types/modal'
import { AvailableMachinesSelector } from '@/components/resources/AvailableMachinesSelector'
import {
  ModalStack,
  ModalPlaceholder,
  SelectedCountTag,
  ModalTitle,
  ModalTitleIcon,
} from '../styles'

interface AssignMachinesModalProps {
  open: boolean
  availableMachines: AvailableMachine[]
  selectedMachines: string[]
  isLoading: boolean
  isSubmitting: boolean
  onSelectionChange: (machines: string[]) => void
  onAssign: () => void
  onCancel: () => void
  t: TFunction<'distributedStorage' | 'machines' | 'common'>
}

export const AssignMachinesModal: React.FC<AssignMachinesModalProps> = ({
  open,
  availableMachines,
  selectedMachines,
  isLoading,
  isSubmitting,
  onSelectionChange,
  onAssign,
  onCancel,
  t,
}) => (
  <Modal
    title={
      <ModalTitle>
        <ModalTitleIcon />
        {t('distributedStorage:clones.assignMachines')}
      </ModalTitle>
    }
    open={open}
    onCancel={onCancel}
    onOk={onAssign}
    okText={t('machines:assignToClone')}
    cancelText={t('common:actions.cancel')}
    confirmLoading={isSubmitting}
    okButtonProps={{
      disabled: selectedMachines.length === 0,
      'data-testid': 'clone-manager-modal-ok',
    }}
    cancelButtonProps={{
      'data-testid': 'clone-manager-modal-cancel',
    }}
    className={ModalSize.Large}
    data-testid="clone-manager-modal-add"
  >
    <ModalStack>
      <Alert
        message={t('distributedStorage:clones.assignMachinesInfo')}
        type="info"
        showIcon
        data-testid="clone-manager-modal-alert"
      />
      {isLoading ? (
        <ModalPlaceholder data-testid="clone-manager-modal-loading">
          <Spin />
        </ModalPlaceholder>
      ) : availableMachines.length === 0 ? (
        <Empty
          description={t('machines:noAvailableMachinesForClone')}
          data-testid="clone-manager-modal-empty"
        />
      ) : (
        <AvailableMachinesSelector
          machines={availableMachines as unknown as Machine[]}
          value={selectedMachines}
          onChange={onSelectionChange}
          data-testid="clone-manager-modal-selector"
        />
      )}
      {selectedMachines.length > 0 && (
        <SelectedCountTag data-testid="clone-manager-modal-selected-count">
          {t('machines:bulkOperations.selectedCount', {
            count: selectedMachines.length,
          })}
        </SelectedCountTag>
      )}
    </ModalStack>
  </Modal>
)
