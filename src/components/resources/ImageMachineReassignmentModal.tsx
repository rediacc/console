import React, { useState } from 'react'
import { Modal, Select, Space, Typography, Spin, Alert } from 'antd'
import { CloudServerOutlined, FileImageOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import type { DistributedStorageRbdImage } from '@/api/queries/distributedStorage'
import { useGetAvailableMachinesForClone, useUpdateImageMachineAssignment } from '@/api/queries/distributedStorage'
import { useComponentStyles, useFormStyles } from '@/hooks/useComponentStyles'
import { ModalSize } from '@/types/modal'

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
  
  const styles = useComponentStyles()
  const formStyles = useFormStyles()
  const [prevOpen, setPrevOpen] = useState(open)

  // Fetch available machines
  const { data: availableMachines = [], isLoading: loadingMachines } = useGetAvailableMachinesForClone(
    teamName,
    open && !!image
  )

  // Sync state with open prop during render
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (!open) {
      setSelectedMachine('')
    }
  }
  
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
        <Space style={styles.flexStart}>
          <FileImageOutlined style={styles.icon.medium} />
          <span style={styles.heading4}>{t('distributedStorage:images.reassignMachine')}</span>
        </Space>
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
        style: {
          ...styles.buttonPrimary,
          ...styles.controlSurface
        }
      }}
      cancelButtonProps={{
        'data-testid': 'image-reassign-cancel',
        style: {
          ...styles.buttonSecondary,
          ...styles.controlSurface
        }
      }}
      className={ModalSize.Medium}
      data-testid="image-reassign-modal"
    >
      {image && (
        <Space 
          direction="vertical" 
          size="large" 
          style={{ 
            width: '100%',
            ...styles.padding.md
          }}
        >
          <div>
            <Text strong style={styles.label}>{t('distributedStorage:images.image')}: </Text>
            <Text style={styles.body}>{image.imageName}</Text>
          </div>
          
          <div>
            <Text strong style={styles.label}>{t('distributedStorage:pools.pool')}: </Text>
            <Text style={styles.body}>{poolName}</Text>
          </div>
          
          {image.machineName && (
            <Alert
              message={
                <span style={styles.body}>
                  {t('machines:currentMachineAssignment', { 
                    machine: image.machineName 
                  })}
                </span>
              }
              type="info"
              showIcon
              icon={<CloudServerOutlined style={styles.icon.small} />}
              style={{
                borderRadius: 'var(--border-radius-lg)'
              }}
              data-testid="image-reassign-current-machine-info"
            />
          )}
          
          <div>
            <Text 
              strong 
              style={{ 
                display: 'block',
                ...styles.marginBottom.xs,
                ...styles.label
              }}
            >
              {t('distributedStorage:images.selectNewMachine')}:
            </Text>
            {loadingMachines ? (
              <div style={styles.flexCenter}>
                <Spin data-testid="image-reassign-loading" />
              </div>
            ) : (
              <>
                <Select
                  style={{
                    width: '100%',
                    ...formStyles.formInput
                  }}
                  placeholder={t('machines:selectMachine')}
                  value={selectedMachine}
                  onChange={setSelectedMachine}
                  showSearch
                  optionFilterProp="children"
                  notFoundContent={
                    availableMachines.length === 0 
                      ? <span style={styles.body}>{t('machines:noAvailableMachines')}</span>
                      : <span style={styles.body}>{t('common:noMatchingResults')}</span>
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
                      <span style={{
                        ...styles.body,
                        opacity: 0.6
                      }}>
                        {image.machineName} ({t('common:current')})
                      </span>
                    </Select.Option>
                  )}
                  
                  {/* Available machines */}
                  {availableMachines.map(machine => (
                    <Select.Option 
                      key={machine.machineName} 
                      value={machine.machineName}
                      data-testid={`image-reassign-machine-option-${machine.machineName}`}
                    >
                      <span style={styles.body}>{machine.machineName}</span>
                    </Select.Option>
                  ))}
                </Select>
                
                <Text 
                  type="secondary" 
                  style={{ 
                    display: 'block',
                    ...styles.marginBottom.xs,
                    ...styles.caption
                  }}
                >
                  {t('distributedStorage:images.reassignmentInfo')}
                </Text>
              </>
            )}
          </div>
          
          <Alert
            message={<span style={styles.label}>{t('common:important')}</span>}
            description={
              <span style={styles.body}>
                {t('distributedStorage:images.reassignmentWarning')}
              </span>
            }
            type="warning"
            showIcon
            style={{
              borderRadius: 'var(--border-radius-lg)'
            }}
            data-testid="image-reassign-warning"
          />
        </Space>
      )}
    </Modal>
  )
}