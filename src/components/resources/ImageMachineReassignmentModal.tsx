import React, { useState, useEffect } from 'react'
import { Modal, Select, Space, Typography, Spin, Alert } from 'antd'
import { CloudServerOutlined, FileImageOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { DistributedStorageRbdImage } from '@/api/queries/distributedStorage'
import { useGetAvailableMachinesForClone, useUpdateImageMachineAssignment } from '@/api/queries/distributedStorage'
import { showMessage } from '@/utils/messages'

const { Text } = Typography

interface ImageMachineReassignmentModalProps {
  open: boolean
  image: DistributedStorageRbdImage | null
  teamName: string
  poolName: string
  onCancel: () => void
  onSuccess?: () => void
}

export const ImageMachineReassignmentModal: React.FC<ImageMachineReassignmentModalProps> = ({
  open,
  image,
  teamName,
  poolName,
  onCancel,
  onSuccess
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines', 'common'])
  const [selectedMachine, setSelectedMachine] = useState<string>('')
  const updateMachineAssignment = useUpdateImageMachineAssignment()
  
  // Fetch available machines
  const { data: availableMachines = [], isLoading: loadingMachines } = useGetAvailableMachinesForClone(
    teamName,
    open && !!image
  )
  
  // Reset selected machine when modal opens/closes
  useEffect(() => {
    if (!open) {
      setSelectedMachine('')
    }
  }, [open])
  
  const handleOk = async () => {
    if (!image || !selectedMachine) return
    
    try {
      await updateMachineAssignment.mutateAsync({
        teamName,
        poolName,
        imageName: image.imageName,
        newMachineName: selectedMachine
      })
      
      if (onSuccess) onSuccess()
      onCancel()
    } catch (error) {
      // Error is handled by the mutation hook
    }
  }
  
  return (
    <Modal
      title={
        <Space>
          <FileImageOutlined />
          {t('distributedStorage:images.reassignMachine')}
        </Space>
      }
      open={open}
      onOk={handleOk}
      onCancel={onCancel}
      okText={t('common:actions.save')}
      cancelText={t('common:actions.cancel')}
      confirmLoading={updateMachineAssignment.isPending}
      okButtonProps={{ 
        disabled: !selectedMachine || selectedMachine === image?.machineName 
      }}
      width={600}
    >
      {image && (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div>
            <Text strong>{t('distributedStorage:images.image')}: </Text>
            <Text>{image.imageName}</Text>
          </div>
          
          <div>
            <Text strong>{t('distributedStorage:pools.pool')}: </Text>
            <Text>{poolName}</Text>
          </div>
          
          {image.machineName && (
            <Alert
              message={t('machines:currentMachineAssignment', { 
                machine: image.machineName 
              })}
              type="info"
              showIcon
              icon={<CloudServerOutlined />}
            />
          )}
          
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              {t('distributedStorage:images.selectNewMachine')}:
            </Text>
            {loadingMachines ? (
              <Spin />
            ) : (
              <>
                <Select
                  style={{ width: '100%' }}
                  placeholder={t('machines:selectMachine')}
                  value={selectedMachine}
                  onChange={setSelectedMachine}
                  showSearch
                  optionFilterProp="children"
                  notFoundContent={
                    availableMachines.length === 0 
                      ? t('machines:noAvailableMachines')
                      : t('common:noMatchingResults')
                  }
                >
                  {/* Include current machine if it exists */}
                  {image.machineName && (
                    <Select.Option 
                      key={image.machineName} 
                      value={image.machineName}
                      disabled
                    >
                      {image.machineName} ({t('common:current')})
                    </Select.Option>
                  )}
                  
                  {/* Available machines */}
                  {availableMachines.map(machine => (
                    <Select.Option 
                      key={machine.machineName} 
                      value={machine.machineName}
                    >
                      {machine.machineName}
                    </Select.Option>
                  ))}
                </Select>
                
                <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                  {t('distributedStorage:images.reassignmentInfo')}
                </Text>
              </>
            )}
          </div>
          
          <Alert
            message={t('common:important')}
            description={t('distributedStorage:images.reassignmentWarning')}
            type="warning"
            showIcon
          />
        </Space>
      )}
    </Modal>
  )
}