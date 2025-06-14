import React, { useRef, useEffect, useState } from 'react'
import { Modal, Button, Space, Typography, Upload } from 'antd'
import { UploadOutlined, DownloadOutlined } from '@ant-design/icons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import ResourceFormWithVault from '@/components/forms/ResourceFormWithVault'
import VaultEditorModal from '@/components/common/VaultEditorModal'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import { useDropdownData } from '@/api/queries/useDropdownData'
import {
  createMachineSchema,
  createRepositorySchema,
  createStorageSchema,
  createScheduleSchema,
  createTeamSchema,
  createRegionSchema,
  createBridgeSchema,
  CreateMachineForm,
  CreateRepositoryForm,
  CreateStorageForm,
  CreateScheduleForm,
} from '@/utils/validation'
import { z } from 'zod'

const { Text } = Typography

export type ResourceType = 'machine' | 'repository' | 'storage' | 'schedule' | 'team' | 'region' | 'bridge'

export interface UnifiedResourceModalProps {
  open: boolean
  onCancel: () => void
  resourceType: ResourceType
  mode: 'create' | 'edit' | 'vault'
  existingData?: any
  teamFilter?: string | string[]
  onSubmit: (data: any) => Promise<void>
  onUpdateVault?: (vault: string, version: number) => Promise<void>
  onFunctionSubmit?: (functionData: any) => Promise<void>
  isSubmitting?: boolean
  isUpdatingVault?: boolean
  functionCategories?: string[]
  hiddenParams?: string[]
  defaultParams?: Record<string, any>
}

const UnifiedResourceModal: React.FC<UnifiedResourceModalProps> = ({
  open,
  onCancel,
  resourceType,
  mode,
  existingData,
  teamFilter,
  onSubmit,
  onUpdateVault,
  onFunctionSubmit,
  isSubmitting = false,
  isUpdatingVault = false,
  functionCategories = [],
  hiddenParams = [],
  defaultParams = {},
}) => {
  const { t } = useTranslation(['resources', 'machines', 'common'])
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const isExpertMode = uiMode === 'expert'
  const { data: dropdownData } = useDropdownData()
  const formRef = useRef<any>(null)

  // State for modal dimensions
  const [modalDimensions, setModalDimensions] = useState({
    width: '90vw',
    height: '85vh',
    top: '5vh'
  })

  // State for sub-modals
  const [showVaultModal, setShowVaultModal] = useState(false)
  const [showFunctionModal, setShowFunctionModal] = useState(false)
  
  // Import/Export handlers ref
  const importExportHandlers = useRef<{ handleImport: (file: any) => boolean; handleExport: () => void } | null>(null)
  
  // Resource configuration
  const RESOURCE_CONFIG = {
    storage: { key: 'storage', createKey: 'resources:storage.createStorage' },
    repository: { key: 'repositories', createKey: 'resources:repositories.createRepository' },
    machine: { key: 'machines', createKey: 'machines:createMachine' },
    schedule: { key: 'schedules', createKey: 'resources:schedules.createSchedule' },
    team: { key: 'teams', createKey: 'system:teams.createTeam' },
    region: { key: 'regions', createKey: 'system:regions.createRegion' },
    bridge: { key: 'bridges', createKey: 'system:bridges.createBridge' }
  } as const

  // Helper functions
  const getResourceTranslationKey = () => RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.key || `${resourceType}s`
  const mapToOptions = (items: any[] | undefined) => items?.map(item => ({ value: item.value, label: item.label })) || []

  // Calculate modal dimensions based on viewport
  useEffect(() => {
    const calculateModalDimensions = () => {
      const vw = window.innerWidth
      
      let widthPercent = 90
      let heightPercent = 85
      let topPercent = 5
      
      if (vw >= 3840) { // 4K
        widthPercent = 95
        heightPercent = 92
        topPercent = 3
      } else if (vw >= 2560) { // 2K
        widthPercent = 92
        heightPercent = 88
        topPercent = 4
      }
      
      setModalDimensions({
        width: `${widthPercent}vw`,
        height: `${heightPercent}vh`,
        top: `${topPercent}vh`
      })
    }
    
    calculateModalDimensions()
    window.addEventListener('resize', calculateModalDimensions)
    
    return () => {
      window.removeEventListener('resize', calculateModalDimensions)
    }
  }, [])

  // Schema mapping
  const SCHEMA_MAP = {
    machine: uiMode === 'simple' ? z.object({
      machineName: z.string().min(1, 'Machine name is required'),
      teamName: z.string().optional(),
      regionName: z.string().optional(),
      bridgeName: z.string().optional(),
      machineVault: z.string().optional().default('{}'),
    }) : createMachineSchema,
    repository: createRepositorySchema,
    storage: createStorageSchema,
    schedule: createScheduleSchema,
    team: createTeamSchema,
    region: createRegionSchema,
    bridge: createBridgeSchema
  }

  const getSchema = () => {
    if (mode === 'edit') {
      return z.object({
        [`${resourceType}Name`]: z.string().min(1, `${resourceType} name is required`),
        ...(resourceType === 'machine' && { regionName: z.string().optional(), bridgeName: z.string().optional() }),
      })
    }
    return SCHEMA_MAP[resourceType as keyof typeof SCHEMA_MAP] || z.object({})
  }

  // Default values factory
  const getDefaultValues = () => {
    if (mode === 'edit' && existingData) {
      return {
        [`${resourceType}Name`]: existingData[`${resourceType}Name`],
        ...(resourceType === 'machine' && { regionName: existingData.regionName, bridgeName: existingData.bridgeName }),
        ...(resourceType === 'bridge' && { regionName: existingData.regionName }),
        [`${resourceType}Vault`]: existingData.vaultContent || '{}',
      }
    }

    const baseDefaults = {
      teamName: uiMode === 'simple' ? 'Private Team' : '',
      [`${resourceType}Vault`]: '{}',
      [`${resourceType}Name`]: '',
    }

    const resourceDefaults = {
      machine: {
        regionName: uiMode === 'simple' ? 'Default Region' : '',
        bridgeName: uiMode === 'simple' ? 'Global Bridges' : '',
        machineVault: '{}',
      },
      team: { teamName: '', teamVault: '{}' },
      region: { regionName: '', regionVault: '{}' },
      bridge: { regionName: '', bridgeName: '', bridgeVault: '{}' },
    }

    return { ...baseDefaults, ...resourceDefaults[resourceType as keyof typeof resourceDefaults] }
  }

  const form = useForm({
    resolver: zodResolver(getSchema()) as any,
    defaultValues: getDefaultValues(),
  })

  // Watch form values for dependent fields (machines only)
  const selectedRegion = resourceType === 'machine' ? form.watch('regionName') : null

  // Get filtered bridges based on selected region
  const filteredBridges = React.useMemo(() => {
    if (!selectedRegion || !dropdownData?.bridgesByRegion) return []
    
    const regionData = dropdownData.bridgesByRegion.find(
      (r: any) => r.regionName === selectedRegion
    )
    return regionData?.bridges?.map((b: any) => ({ 
      value: b.value, 
      label: b.label 
    })) || []
  }, [selectedRegion, dropdownData])

  // Clear bridge selection when region changes
  useEffect(() => {
    if (resourceType === 'machine' && selectedRegion) {
      const currentBridge = form.getValues('bridgeName')
      if (currentBridge && !filteredBridges.find((b: any) => b.value === currentBridge)) {
        form.setValue('bridgeName', '')
      }
    }
  }, [selectedRegion, filteredBridges, form, resourceType])

  // Set default values when modal opens
  useEffect(() => {
    if (open && mode === 'create') {
      // Set team if preselected
      if (teamFilter) {
        if (Array.isArray(teamFilter) && teamFilter.length === 1) {
          form.setValue('teamName', teamFilter[0])
        } else if (!Array.isArray(teamFilter)) {
          form.setValue('teamName', teamFilter)
        }
      }

      // For machines, set default region and bridge
      if (resourceType === 'machine' && dropdownData?.regions && dropdownData.regions.length > 0) {
        const firstRegion = dropdownData.regions[0].value
        form.setValue('regionName', firstRegion)
        
        const regionBridges = dropdownData.bridgesByRegion?.find(
          (region: any) => region.regionName === firstRegion
        )
        
        if (regionBridges?.bridges && regionBridges.bridges.length > 0) {
          const firstBridge = regionBridges.bridges[0].value
          form.setValue('bridgeName', firstBridge)
        }
      }
    }
  }, [open, mode, teamFilter, resourceType, form, dropdownData])

  // Reset form values when modal opens in edit mode
  useEffect(() => {
    if (open && mode === 'edit' && existingData) {
      form.reset({
        [`${resourceType}Name`]: existingData[`${resourceType}Name`],
        ...(resourceType === 'machine' && {
          regionName: existingData.regionName,
          bridgeName: existingData.bridgeName,
        }),
        ...(resourceType === 'bridge' && {
          regionName: existingData.regionName,
        }),
        [`${resourceType}Vault`]: existingData.vaultContent || '{}',
      })
    }
  }, [open, mode, existingData, resourceType, form])

  // Determine if team is already selected/known
  const isTeamPreselected = uiMode === 'simple' || 
    (teamFilter && !Array.isArray(teamFilter)) || 
    (teamFilter && Array.isArray(teamFilter) && teamFilter.length === 1)

  // Field factories
  const createNameField = () => ({
    name: `${resourceType}Name`,
    label: t(`${getResourceTranslationKey()}.${resourceType}Name`),
    placeholder: t(`${getResourceTranslationKey()}.placeholders.enter${resourceType.charAt(0).toUpperCase() + resourceType.slice(1)}Name`),
    required: true,
  })

  const createTeamField = () => ({
    name: 'teamName',
    label: t('general.team'),
    placeholder: t('teams.placeholders.selectTeam'),
    required: true,
    type: 'select' as const,
    options: mapToOptions(dropdownData?.teams),
  })

  const createRegionField = () => ({
    name: 'regionName',
    label: t('general.region'),
    placeholder: t('regions.placeholders.selectRegion'),
    required: true,
    type: 'select' as const,
    options: mapToOptions(dropdownData?.regions),
  })

  const createBridgeField = () => ({
    name: 'bridgeName',
    label: t('bridges.bridge'),
    placeholder: selectedRegion ? t('bridges.placeholders.selectBridge') : t('bridges.placeholders.selectRegionFirst'),
    required: true,
    type: 'select' as const,
    options: filteredBridges,
    disabled: !selectedRegion,
  })

  // Get form fields based on resource type and mode
  const getFormFields = () => {
    const nameField = createNameField()
    
    if (mode === 'edit') {
      if (resourceType === 'machine') return [nameField, createRegionField(), createBridgeField()]
      if (resourceType === 'bridge') return [nameField, createRegionField()]
      return [nameField]
    }

    if (uiMode === 'simple') return [nameField]

    const fields = []
    if (!isTeamPreselected) fields.push(createTeamField())
    
    if (resourceType === 'machine') {
      fields.push(createRegionField(), createBridgeField(), nameField)
    } else if (resourceType === 'bridge') {
      fields.push(createRegionField(), nameField)
    } else if (!['team', 'region'].includes(resourceType)) {
      fields.push(nameField)
    } else {
      return [nameField]
    }
    
    return fields.length ? fields : [nameField]
  }

  // Helper functions
  const getEntityType = () => resourceType.toUpperCase()
  const getVaultFieldName = () => `${resourceType}Vault`
  
  const createFunctionSubtitle = () => (
    <Space size="small">
      <Text type="secondary">{t('machines:team')}:</Text>
      <Text strong>{existingData.teamName}</Text>
      {['machine', 'repository', 'storage'].includes(resourceType) && (
        <>
          <Text type="secondary" style={{ marginLeft: 16 }}>
            {t(resourceType === 'machine' ? 'machines:machine' : 
               resourceType === 'storage' ? 'resources:storage.storage' : 
               'repositories.repository')}:
          </Text>
          <Text strong>{existingData[`${resourceType}Name`]}</Text>
        </>
      )}
    </Space>
  )
  
  const getFunctionTitle = () => {
    if (resourceType === 'machine') return t('machines:systemFunctions')
    if (resourceType === 'storage') return t('resources:storage.storageFunctions')
    return t(`${getResourceTranslationKey()}.${resourceType}Functions`)
  }

  // Get modal title
  const getModalTitle = () => {
    if (mode === 'create') {
      const createKey = RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.createKey
      const createText = createKey ? t(createKey) : ''
      
      if (isTeamPreselected || uiMode === 'simple') {
        const team = uiMode === 'simple' ? 'Private Team' : (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter)
        return `${createText} in ${team}`
      }
      return createText
    }
    return `${t('resources:general.edit')} ${t(`resources:${getResourceTranslationKey()}.${resourceType}Name`)}`
  }

  // Handle form submission
  const handleSubmit = async (data: any) => {
    if (uiMode === 'simple' && mode === 'create') {
      Object.assign(data, {
        teamName: 'Private Team',
        ...(resourceType === 'machine' && {
          regionName: 'Default Region',
          bridgeName: 'Global Bridges'
        })
      })
    }
    await onSubmit(data)
  }

  // Show functions button only for machines, repositories, and storage
  const showFunctions = (resourceType === 'machine' || resourceType === 'repository' || resourceType === 'storage') && 
    mode === 'create' && 
    existingData &&
    onFunctionSubmit &&
    functionCategories.length > 0

  // Auto-open function modal if we're in create mode with existing data (for repository functions)
  useEffect(() => {
    if (open && mode === 'create' && existingData && showFunctions) {
      // Small delay to ensure proper modal rendering
      setTimeout(() => setShowFunctionModal(true), 100)
    }
  }, [open, mode, existingData, showFunctions])

  // If we're in vault mode, show the vault editor directly
  if (mode === 'vault' && existingData && onUpdateVault) {
    return (
      <VaultEditorModal
        open={open}
        onCancel={onCancel}
        onSave={async (vault, version) => {
          await onUpdateVault(vault, version)
          onCancel()
        }}
        entityType={getEntityType()}
        title={t('general.configureVault', { name: existingData[`${resourceType}Name`] || '' })}
        initialVault={existingData.vaultContent || "{}"}
        initialVersion={existingData.vaultVersion || 1}
        loading={isUpdatingVault}
      />
    )
  }

  // If we're showing functions directly, don't show the main modal
  if (mode === 'create' && existingData && showFunctions && showFunctionModal) {
    return (
      <>
        {/* Function Selection Modal */}
        <FunctionSelectionModal
          open={showFunctionModal}
          onCancel={() => {
            setShowFunctionModal(false)
            onCancel()
          }}
          onSubmit={async (functionData) => {
            await onFunctionSubmit(functionData)
            setShowFunctionModal(false)
            onCancel()
          }}
          title={getFunctionTitle()}
          subtitle={createFunctionSubtitle()}
          allowedCategories={functionCategories}
          loading={isSubmitting}
          showMachineSelection={resourceType === 'repository' || resourceType === 'storage'}
          teamName={existingData?.teamName}
          machines={dropdownData?.machinesByTeam?.find(t => t.teamName === existingData?.teamName)?.machines || []}
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
        />
      </>
    )
  }

  return (
    <>
      <Modal
        title={getModalTitle()}
        open={open}
        onCancel={onCancel}
        footer={[
          // Left side buttons (only in create mode)
          ...(mode === 'create' ? [
            <div key="left-buttons" style={{ float: 'left' }}>
              <Space>
                <Upload
                  accept=".json"
                  showUploadList={false}
                  beforeUpload={(file) => {
                    if (importExportHandlers.current) {
                      return importExportHandlers.current.handleImport(file)
                    }
                    return false
                  }}
                >
                  <Button icon={<UploadOutlined />}>{t('common:vaultEditor.importJson')}</Button>
                </Upload>
                <Button 
                  icon={<DownloadOutlined />} 
                  onClick={() => {
                    if (importExportHandlers.current) {
                      importExportHandlers.current.handleExport()
                    }
                  }}
                >
                  {t('common:vaultEditor.exportJson')}
                </Button>
              </Space>
            </div>
          ] : []),
          // Right side buttons
          <Button key="cancel" onClick={onCancel}>
            {t('general.cancel')}
          </Button>,
          ...(mode === 'create' && existingData && onUpdateVault ? [
            <Button 
              key="vault"
              onClick={() => setShowVaultModal(true)}
            >
              {t('general.vault')}
            </Button>
          ] : []),
          ...(showFunctions ? [
            <Button 
              key="functions"
              onClick={() => setShowFunctionModal(true)}
            >
              {t(`${resourceType}s.${resourceType}Functions`)}
            </Button>
          ] : []),
          <Button
            key="submit"
            type="primary"
            loading={isSubmitting}
            onClick={() => formRef.current?.submit()}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            {mode === 'create' ? t('general.create') : t('general.save')}
          </Button>
        ]}
        width={modalDimensions.width}
        style={{ 
          top: modalDimensions.top,
          maxHeight: modalDimensions.height
        }}
        styles={{
          body: {
            height: `calc(${modalDimensions.height} - 120px)`,
            overflowY: 'auto'
          }
        }}
      >
        <ResourceFormWithVault
          ref={formRef}
          form={form}
          fields={getFormFields()}
          onSubmit={handleSubmit}
          entityType={getEntityType()}
          vaultFieldName={getVaultFieldName()}
          showDefaultsAlert={mode === 'create' && uiMode === 'simple'}
          initialVaultData={mode === 'edit' && existingData ? JSON.parse(existingData.vaultContent || '{}') : undefined}
          hideImportExport={true}
          onImportExportRef={(handlers) => {
            importExportHandlers.current = handlers
          }}
          defaultsContent={
            <Space direction="vertical" size={0}>
              <Text>{t('general.team')}: Private Team</Text>
              {resourceType === 'machine' && (
                <>
                  <Text>{t('machines:region')}: Default Region</Text>
                  <Text>{t('machines:bridge')}: Global Bridges</Text>
                </>
              )}
            </Space>
          }
        />
      </Modal>

      {/* Vault Editor Modal */}
      {existingData && onUpdateVault && (
        <VaultEditorModal
          open={showVaultModal}
          onCancel={() => setShowVaultModal(false)}
          onSave={async (vault, version) => {
            await onUpdateVault(vault, version)
            setShowVaultModal(false)
          }}
          entityType={getEntityType()}
          title={t('general.configureVault', { name: existingData[`${resourceType}Name`] || '' })}
          initialVault={existingData.vaultContent || "{}"}
          initialVersion={existingData.vaultVersion || 1}
          loading={isUpdatingVault}
        />
      )}

      {/* Function Selection Modal */}
      {showFunctions && existingData && (
        <FunctionSelectionModal
          open={showFunctionModal}
          onCancel={() => setShowFunctionModal(false)}
          onSubmit={async (functionData) => {
            await onFunctionSubmit(functionData)
            setShowFunctionModal(false)
          }}
          title={getFunctionTitle()}
          subtitle={createFunctionSubtitle()}
          allowedCategories={functionCategories}
          loading={isSubmitting}
          showMachineSelection={resourceType === 'repository'}
          teamName={existingData?.teamName}
          machines={dropdownData?.machinesByTeam?.find(t => t.teamName === existingData?.teamName)?.machines || []}
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
        />
      )}
    </>
  )
}

export default UnifiedResourceModal