import React, { useRef, useEffect, useState } from 'react'
import { Modal, Button, Space, Typography, Upload, message, Collapse, Tag, Checkbox } from 'antd'

// message.error is imported from antd
import { UploadOutlined, DownloadOutlined, AppstoreOutlined } from '@/utils/optimizedIcons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import ResourceFormWithVault from '@/components/forms/ResourceFormWithVault'
import VaultEditorModal from '@/components/common/VaultEditorModal'
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal'
import TemplateSelector from '@/components/common/TemplateSelector'
import TemplateDetailsModal from '@/components/common/TemplateDetailsModal'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius, fontSize } from '@/utils/styleConstants'
import {
  createMachineSchema,
  createRepositorySchema,
  createStorageSchema,
  createScheduleSchema,
  createTeamSchema,
  createRegionSchema,
  createBridgeSchema,
  createClusterSchema,
  createPoolSchema,
  createImageSchema,
  createSnapshotSchema,
  createCloneSchema,
  CreateMachineForm,
  CreateRepositoryForm,
  CreateStorageForm,
  CreateScheduleForm,
  CreateClusterForm,
  CreatePoolForm,
  CreateImageForm,
  CreateSnapshotForm,
  CreateCloneForm,
} from '@/utils/validation'
import { z } from 'zod'
import { ModalSize } from '@/types/modal'

const { Text } = Typography

export type ResourceType = 'machine' | 'repository' | 'storage' | 'schedule' | 'team' | 'region' | 'bridge' | 'cluster' | 'pool' | 'image' | 'snapshot' | 'clone'

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
  preselectedFunction?: string
  creationContext?: 'credentials-only' | 'normal'
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
  preselectedFunction,
  creationContext,
}) => {
  const { t } = useTranslation(['resources', 'machines', 'common', 'distributedStorage', 'system'])
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const isExpertMode = uiMode === 'expert'
  const { data: dropdownData } = useDropdownData()
  const formRef = useRef<any>(null)
  const styles = useComponentStyles()

  // State for sub-modals
  const [showVaultModal, setShowVaultModal] = useState(false)
  const [showFunctionModal, setShowFunctionModal] = useState(false)
  
  // State for test connection (for machines)
  const [testConnectionSuccess, setTestConnectionSuccess] = useState(false)
  
  // Track test connection state changes
  useEffect(() => {
    // Test connection state updated
  }, [testConnectionSuccess, resourceType, mode])
  
  // State for auto-setup after machine creation
  const [autoSetupEnabled, setAutoSetupEnabled] = useState(true)
  
  // State for keeping repository open after creation
  const [keepRepositoryOpen, setKeepRepositoryOpen] = useState(true)
  
  // State for template selection (for repositories)
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(existingData?.preselectedTemplate || null)
  const [showTemplateDetails, setShowTemplateDetails] = useState(false)
  const [templateToView, setTemplateToView] = useState<string | null>(null)
  
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
    bridge: { key: 'bridges', createKey: 'system:bridges.createBridge' },
    cluster: { key: 'clusters', createKey: 'distributedStorage:clusters.createCluster' },
    pool: { key: 'pools', createKey: 'distributedStorage:pools.createPool' },
    image: { key: 'images', createKey: 'distributedStorage:images.createImage' },
    snapshot: { key: 'snapshots', createKey: 'distributedStorage:snapshots.createSnapshot' },
    clone: { key: 'clones', createKey: 'distributedStorage:clones.createClone' }
  } as const

  // Helper functions
  const getResourceTranslationKey = () => RESOURCE_CONFIG[resourceType as keyof typeof RESOURCE_CONFIG]?.key || `${resourceType}s`
  const mapToOptions = (items: any[] | undefined) => items?.map(item => ({ value: item.value, label: item.label })) || []

  // Log when modal opens
  useEffect(() => {
    if (open) {
      // Modal opened with resource configuration
    }
  }, [open, resourceType, mode, uiMode, existingData, teamFilter])

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
    bridge: createBridgeSchema,
    cluster: createClusterSchema,
    pool: createPoolSchema,
    image: createImageSchema,
    snapshot: createSnapshotSchema,
    clone: createCloneSchema
  }

  const getSchema = () => {
    if (mode === 'edit') {
      return z.object({
        [`${resourceType}Name`]: z.string().min(1, `${resourceType} name is required`),
        ...(resourceType === 'machine' && { regionName: z.string().optional(), bridgeName: z.string().optional() }),
      })
    }

    // For repository creation in credentials-only mode, use simpler validation
    if (resourceType === 'repository' && creationContext === 'credentials-only') {
      return z.object({
        teamName: z.string().min(1, 'Team name is required'),
        repositoryName: z.string().min(1, 'Repository name is required'),
        repositoryVault: z.string().optional().default('{}'),
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
        ...(resourceType === 'pool' && { clusterName: existingData.clusterName }),
        ...(resourceType === 'image' && { poolName: existingData.poolName }),
        ...(resourceType === 'snapshot' && { poolName: existingData.poolName, imageName: existingData.imageName }),
        ...(resourceType === 'clone' && { poolName: existingData.poolName, imageName: existingData.imageName, snapshotName: existingData.snapshotName }),
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
      repository: {
        machineName: '',
        size: '',
        repositoryGuid: '',  // Add default for repositoryGuid
      },
      team: { teamName: '', teamVault: '{}' },
      region: { regionName: '', regionVault: '{}' },
      bridge: { regionName: '', bridgeName: '', bridgeVault: '{}' },
      cluster: { clusterName: '', clusterVault: '{}' },
      pool: { clusterName: '', poolName: '', poolVault: '{}' },
      image: { poolName: '', imageName: '', imageVault: '{}' },
      snapshot: { poolName: '', imageName: '', snapshotName: '', snapshotVault: '{}' },
      clone: { poolName: '', imageName: '', snapshotName: '', cloneName: '', cloneVault: '{}' },
    }

    // Merge existingData to override defaults if provided
    const finalDefaults = { ...baseDefaults, ...resourceDefaults[resourceType as keyof typeof resourceDefaults] }
    if (existingData) {
      Object.keys(existingData).forEach(key => {
        if (existingData[key] !== undefined) {
          finalDefaults[key] = existingData[key]
        }
      })
    }

    return finalDefaults
  }

  const form = useForm({
    resolver: zodResolver(getSchema()) as any,
    defaultValues: getDefaultValues(),
  })

  // Get filtered bridges based on selected region - moved inside getFormFields to avoid unnecessary re-renders
  const getFilteredBridges = (regionName: string | null) => {
    if (!regionName || !dropdownData?.bridgesByRegion) return []
    
    const regionData = dropdownData.bridgesByRegion.find(
      (r: any) => r.regionName === regionName
    )
    return regionData?.bridges?.map((b: any) => ({ 
      value: b.value, 
      label: b.label 
    })) || []
  }

  // Clear bridge selection when region changes
  useEffect(() => {
    if (resourceType === 'machine') {
      const subscription = form.watch((value, { name }) => {
        if (name === 'regionName' && value.regionName) {
          const currentBridge = form.getValues('bridgeName')
          const filteredBridges = getFilteredBridges(value.regionName)
          if (currentBridge && !filteredBridges.find((b: any) => b.value === currentBridge)) {
            form.setValue('bridgeName', '')
          }
        }
      })
      return () => subscription.unsubscribe()
    }
  }, [form, resourceType, getFilteredBridges])

  // Set default values when modal opens
  useEffect(() => {
    if (open && mode === 'create') {
      // Reset form to default values first
      form.reset(getDefaultValues())
      
      // Reset template selection for repositories (unless preselected)
      if (resourceType === 'repository' && !existingData?.preselectedTemplate) {
        setSelectedTemplate(null)
      } else if (resourceType === 'repository' && existingData?.preselectedTemplate) {
        setSelectedTemplate(existingData.preselectedTemplate)
      }
      
      // Set team if preselected or from existing data
      if (existingData?.teamName) {
        form.setValue('teamName', existingData.teamName)
      } else if (teamFilter) {
        if (Array.isArray(teamFilter) && teamFilter.length === 1) {
          form.setValue('teamName', teamFilter[0])
        } else if (!Array.isArray(teamFilter)) {
          form.setValue('teamName', teamFilter)
        }
      }

      // For repositories, set prefilled machine
      if (resourceType === 'repository' && existingData?.machineName) {
        form.setValue('machineName', existingData.machineName)
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
  }, [open, mode, teamFilter, resourceType, form, dropdownData, existingData])

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
        ...(resourceType === 'pool' && {
          clusterName: existingData.clusterName,
        }),
        ...(resourceType === 'image' && {
          poolName: existingData.poolName,
        }),
        ...(resourceType === 'snapshot' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
        }),
        ...(resourceType === 'clone' && {
          poolName: existingData.poolName,
          imageName: existingData.imageName,
          snapshotName: existingData.snapshotName,
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

  const createBridgeField = () => {
    const currentRegion = form.getValues('regionName')
    const bridgeOptions = getFilteredBridges(currentRegion)
    return {
      name: 'bridgeName',
      label: t('bridges.bridge'),
      placeholder: currentRegion ? t('bridges.placeholders.selectBridge') : t('bridges.placeholders.selectRegionFirst'),
      required: true,
      type: 'select' as const,
      options: bridgeOptions,
      disabled: !currentRegion,
    }
  }

  // Get form fields based on resource type and mode
  const getFormFields = () => {
    const nameField = createNameField()
    
    if (mode === 'edit') {
      if (resourceType === 'machine') return [nameField, createRegionField(), createBridgeField()]
      if (resourceType === 'bridge') return [nameField, createRegionField()]
      // For repositories in edit mode, we still need to show the vault fields
      // so users can update credentials if needed
      if (resourceType === 'repository') {
        // Don't include team field in edit mode since team can't be changed
        return [nameField]
      }
      return [nameField]
    }

    if (uiMode === 'simple') {
      const simpleFields = [nameField]
      
      // For repository creation, we need to include size field and potentially machine selection
      if (resourceType === 'repository') {
        // Check if machine is prefilled
        const isPrefilledMachine = existingData?.prefilledMachine
        
        // Check if this is credential-only mode (either from Add Credential button or Repo Credentials tab)
        const isCredentialOnlyMode = (existingData?.repositoryGuid && existingData?.repositoryGuid.trim() !== '') || creationContext === 'credentials-only'
        
        // Get machines for the team (use existingData teamName if available)
        const teamName = existingData?.teamName || 'Private Team'
        const teamMachines = dropdownData?.machinesByTeam?.find(t => t.teamName === teamName)?.machines || []
        
        // Only show machine selection if not prefilled and not in credential-only mode
        if (!isPrefilledMachine && !isCredentialOnlyMode) {
          simpleFields.push({
            name: 'machineName',
            label: t('machines:machine'),
            placeholder: t('machines:placeholders.selectMachine'),
            required: false,
            type: 'select' as const,
            options: teamMachines.map((m: any) => ({ value: m.value, label: m.label })),
            helperText: t('repositories.machineHelperText', { defaultValue: 'Optional: Select a machine to provision storage' })
          })
        }
        
        // Size field for repository provisioning - only show if not in credential-only mode
        if (!isCredentialOnlyMode) {
          simpleFields.push({
            name: 'size',
            label: t('repositories.size'),
            placeholder: t('repositories.placeholders.enterSize'),
            required: false,
            type: 'size' as const,
            sizeUnits: ['G', 'T'],
            helperText: t('repositories.sizeHelperText', { defaultValue: 'Optional: Specify size if provisioning storage (e.g., 10G, 100G, 1T)' })
          })
        }
        
        // Show repositoryGuid field in credential-only mode
        if (isCredentialOnlyMode) {
          simpleFields.push({
            name: 'repositoryGuid',
            label: t('repositories.guid', { defaultValue: 'Repository GUID' }),
            type: 'text' as const,
            disabled: true, // Make it read-only
            helperText: t('repositories.guidHelperText', { defaultValue: 'This repository already exists on the machine.' })
          })
        }
      }
      
      return simpleFields
    }

    const fields = []
    if (!isTeamPreselected) fields.push(createTeamField())
    
    if (resourceType === 'machine') {
      fields.push(createRegionField(), createBridgeField(), nameField)
    } else if (resourceType === 'bridge') {
      fields.push(createRegionField(), nameField)
    } else if (resourceType === 'repository') {
      // Repository creation needs machine selection and size
      fields.push(nameField)
      
      // Check if machine is prefilled
      const isPrefilledMachine = existingData?.prefilledMachine
      
      // Check if this is credential-only mode (either from Add Credential button or Repo Credentials tab)
      const isCredentialOnlyMode = (existingData?.repositoryGuid && existingData?.repositoryGuid.trim() !== '') || creationContext === 'credentials-only'
      
      // Get machines for the selected team
      const selectedTeamName = form.getValues('teamName') || existingData?.teamName || (isTeamPreselected ? (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter) : '')
      const teamMachines = dropdownData?.machinesByTeam?.find(t => t.teamName === selectedTeamName)?.machines || []
      
      // Only show machine selection if not prefilled and not in credential-only mode
      if (!isPrefilledMachine && !isCredentialOnlyMode) {
        fields.push({
          name: 'machineName',
          label: t('machines:machine'),
          placeholder: t('machines:placeholders.selectMachine'),
          required: true,
          type: 'select' as const,
          options: teamMachines.map((m: any) => ({ value: m.value, label: m.label })),
          disabled: !selectedTeamName || teamMachines.length === 0,
          helperText: t('repositories.machineHelperText', { defaultValue: 'Select a machine to provision storage' })
        })
      }
      
      // Only show size field if not in credential-only mode
      if (!isCredentialOnlyMode) {
        fields.push({
          name: 'size',
          label: t('repositories.size'),
          placeholder: t('repositories.placeholders.enterSize'),
          required: true,
          type: 'size' as const,
          sizeUnits: ['G', 'T'],
          helperText: t('repositories.sizeHelperText', { defaultValue: 'Specify size for storage provisioning (e.g., 10G, 100G, 1T)' })
        })
      }
      
      // Repository GUID field
      if (isCredentialOnlyMode) {
        // In credential-only mode, always show the GUID field as read-only
        fields.push({
          name: 'repositoryGuid',
          label: t('repositories.guid', { defaultValue: 'Repository GUID' }),
          type: 'text' as const,
          disabled: true, // Make it read-only
          helperText: t('repositories.guidHelperText', { defaultValue: 'This repository already exists on the machine.' })
        })
      } else if (isExpertMode) {
        // In expert mode (when creating new repo), show as optional editable field
        fields.push({
          name: 'repositoryGuid',
          label: t('repositories.guid', { defaultValue: 'Repository GUID' }),
          placeholder: t('repositories.placeholders.enterGuid', { defaultValue: 'Optional: Enter a specific GUID (e.g., 550e8400-e29b-41d4-a716-446655440000)' }),
          required: false,
          type: 'text' as const,
          helperText: t('repositories.guidHelperText', { defaultValue: 'Optional: Specify a custom GUID for the repository. Leave empty to auto-generate.' })
        })
      }
    } else if (resourceType === 'cluster') {
      fields.push(nameField)
    } else if (resourceType === 'pool') {
      // Get clusters for the selected team
      const selectedTeamName = form.getValues('teamName') || existingData?.teamName || (isTeamPreselected ? (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter) : '')
      const teamClusters = existingData?.clusters || []
      
      fields.push({
        name: 'clusterName',
        label: t('distributedStorage:pools.cluster'),
        placeholder: t('distributedStorage:pools.selectCluster'),
        required: true,
        type: 'select' as const,
        options: teamClusters.map((c: any) => ({ value: c.clusterName, label: c.clusterName })),
        disabled: teamClusters.length === 0,
      })
      fields.push(nameField)
    } else if (resourceType === 'image') {
      // Image needs pool selection and machine assignment
      const selectedTeamName = form.getValues('teamName') || existingData?.teamName || (isTeamPreselected ? (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter) : '')
      const teamPools = existingData?.pools || []
      const availableMachines = existingData?.availableMachines || []
      
      fields.push({
        name: 'poolName',
        label: t('distributedStorage:images.pool'),
        placeholder: t('distributedStorage:images.selectPool'),
        required: true,
        type: 'select' as const,
        options: teamPools.map((p: any) => ({ value: p.poolName, label: `${p.poolName} (${p.clusterName})` })),
        disabled: teamPools.length === 0,
      })
      fields.push(nameField)
      
      // Add machine selection for image creation
      if (mode === 'create') {
        fields.push({
          name: 'machineName',
          label: t('distributedStorage:images.machine'),
          placeholder: t('distributedStorage:images.selectMachine'),
          required: true,
          type: 'select' as const,
          options: availableMachines.map((m: any) => ({ 
            value: m.machineName, 
            label: m.machineName,
            disabled: m.status !== 'AVAILABLE'
          })),
          disabled: availableMachines.length === 0,
          helperText: availableMachines.length === 0 ? t('machines:noMachinesFound') : undefined,
        })
      }
    } else if (resourceType === 'snapshot') {
      // Snapshot needs pool and image selection
      const selectedTeamName = form.getValues('teamName') || existingData?.teamName || (isTeamPreselected ? (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter) : '')
      const teamPools = existingData?.pools || []
      const selectedPoolName = form.getValues('poolName') || existingData?.poolName
      const poolImages = existingData?.images || []
      
      if (!existingData?.poolName) {
        fields.push({
          name: 'poolName',
          label: t('distributedStorage:snapshots.pool'),
          placeholder: t('distributedStorage:snapshots.selectPool'),
          required: true,
          type: 'select' as const,
          options: teamPools.map((p: any) => ({ value: p.poolName, label: `${p.poolName} (${p.clusterName})` })),
          disabled: teamPools.length === 0,
        })
      }
      
      fields.push({
        name: 'imageName',
        label: t('distributedStorage:snapshots.image'),
        placeholder: t('distributedStorage:snapshots.selectImage'),
        required: true,
        type: 'select' as const,
        options: poolImages.map((i: any) => ({ value: i.imageName, label: i.imageName })),
        disabled: !selectedPoolName || poolImages.length === 0,
      })
      fields.push(nameField)
    } else if (resourceType === 'clone') {
      // Clone needs pool, image, and snapshot selection
      const selectedTeamName = form.getValues('teamName') || existingData?.teamName || (isTeamPreselected ? (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter) : '')
      const teamPools = existingData?.pools || []
      const selectedPoolName = form.getValues('poolName') || existingData?.poolName
      const poolImages = existingData?.images || []
      const selectedImageName = form.getValues('imageName') || existingData?.imageName
      const imageSnapshots = existingData?.snapshots || []
      
      if (!existingData?.poolName) {
        fields.push({
          name: 'poolName',
          label: t('distributedStorage:clones.pool'),
          placeholder: t('distributedStorage:clones.selectPool'),
          required: true,
          type: 'select' as const,
          options: teamPools.map((p: any) => ({ value: p.poolName, label: `${p.poolName} (${p.clusterName})` })),
          disabled: teamPools.length === 0,
        })
      }
      
      if (!existingData?.imageName) {
        fields.push({
          name: 'imageName',
          label: t('distributedStorage:clones.image'),
          placeholder: t('distributedStorage:clones.selectImage'),
          required: true,
          type: 'select' as const,
          options: poolImages.map((i: any) => ({ value: i.imageName, label: i.imageName })),
          disabled: !selectedPoolName || poolImages.length === 0,
        })
      }
      
      fields.push({
        name: 'snapshotName',
        label: t('distributedStorage:clones.snapshot'),
        placeholder: t('distributedStorage:clones.selectSnapshot'),
        required: true,
        type: 'select' as const,
        options: imageSnapshots.map((s: any) => ({ value: s.snapshotName, label: s.snapshotName })),
        disabled: !selectedImageName || imageSnapshots.length === 0,
      })
      fields.push(nameField)
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

      // Special case for repository creation
      if (resourceType === 'repository') {
        // Check if this is credential-only mode (either from Add Credential button or Repo Credentials tab)
        const isCredentialOnlyMode = (existingData?.repositoryGuid && existingData?.repositoryGuid.trim() !== '') || creationContext === 'credentials-only'

        if (isCredentialOnlyMode) {
          // For credential-only mode, show "Create Repo (Credentials) in [team]"
          const team = existingData?.teamName || (uiMode === 'simple' ? 'Private Team' : (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter))
          return `Create Repo (Credentials) in ${team}`
        } else if (existingData?.machineName) {
          // For repository creation from machine
          return `${createText} for ${existingData.machineName}`
        }
      }

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
    // Get form fields configuration
    const fields = getFormFields()
    
    // Validate machine creation - check if SSH password is present without SSH key configured
    if (mode === 'create' && resourceType === 'machine') {
      const vaultData = data.machineVault ? JSON.parse(data.machineVault) : {}
      // Only block if password exists AND SSH key is not configured
      if (vaultData.ssh_password && !vaultData.ssh_key_configured) {
        message.error(t('machines:validation.sshPasswordNotAllowed'))
        return
      }
    }
    
    if (uiMode === 'simple' && mode === 'create') {
      // Only set defaults if not already provided
      const defaults: any = {}
      
      // Preserve teamName from existingData if available (e.g., when creating repo from machine)
      if (!data.teamName) {
        if (existingData?.teamName) {
          defaults.teamName = existingData.teamName
        } else {
          defaults.teamName = 'Private Team'
        }
      }
      
      // Set machine-specific defaults
      if (resourceType === 'machine') {
        defaults.regionName = 'Default Region'
        defaults.bridgeName = 'Global Bridges'
      }
      
      Object.assign(data, defaults)
    }
    
    // For repository creation from machine, ensure machine name is included
    if (resourceType === 'repository' && existingData?.machineName && existingData?.prefilledMachine) {
      data.machineName = existingData.machineName
      // Also ensure teamName is preserved
      if (existingData?.teamName && !data.teamName) {
        data.teamName = existingData.teamName
      }
    }
    
    // Add template parameter for repository creation
    if (resourceType === 'repository' && mode === 'create' && selectedTemplate) {
      try {
        // Fetch the template details
        const response = await fetch(`${window.location.origin}/config/template_${selectedTemplate}.json`)
        if (response.ok) {
          const templateData = await response.json()
          // Base64 encode the template JSON
          data.tmpl = btoa(JSON.stringify(templateData))
        }
      } catch (error) {
        message.warning(t('resources:templates.failedToLoadTemplate'))
      }
    }
    
    // Add keep_open flag for repository creation
    if (resourceType === 'repository' && mode === 'create') {
      data.keep_open = keepRepositoryOpen
    }
    
    // Add auto-setup flag for machine creation
    if (mode === 'create' && resourceType === 'machine') {
      data.autoSetup = autoSetupEnabled
    }
    
    await onSubmit(data)
  }

  // Show functions button only for machines, repositories, and storage
  const showFunctions = (resourceType === 'machine' || resourceType === 'repository' || resourceType === 'storage') && 
    mode === 'create' && 
    existingData &&
    !existingData.prefilledMachine && // Don't show functions when creating repo from machine
    onFunctionSubmit &&
    functionCategories.length > 0

  // Auto-open function modal if we're in create mode with existing data (for repository functions)
  useEffect(() => {
    if (open && mode === 'create' && existingData && showFunctions) {
      // Open modal immediately (no delay)
      setShowFunctionModal(true)
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
  if (mode === 'create' && existingData && showFunctions && showFunctionModal && !existingData.prefilledMachine) {
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
          preselectedFunction={preselectedFunction}
        />
      </>
    )
  }

  return (
    <>
      <Modal
        data-testid="resource-modal"
        title={getModalTitle()}
        open={open}
        onCancel={onCancel}
        destroyOnHidden
        footer={[
          // Left side buttons (only in create mode)
          ...(mode === 'create' ? [
            <div key="left-buttons" style={{ float: 'left' }}>
              <Space>
                <Upload
                  data-testid="resource-modal-upload-json"
                  accept=".json"
                  showUploadList={false}
                  beforeUpload={(file) => {
                    if (importExportHandlers.current) {
                      return importExportHandlers.current.handleImport(file)
                    }
                    return false
                  }}
                >
                  <Button 
                    data-testid="resource-modal-import-button" 
                    icon={<UploadOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />}
                    style={{
                      minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                      borderRadius: borderRadius('LG'),
                      fontSize: fontSize('SM')
                    }}
                  >
                    {t('common:vaultEditor.importJson')}
                  </Button>
                </Upload>
                <Button 
                  data-testid="resource-modal-export-button"
                  icon={<DownloadOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />} 
                  onClick={() => {
                    if (importExportHandlers.current) {
                      importExportHandlers.current.handleExport()
                    }
                  }}
                  style={{
                    minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                    borderRadius: borderRadius('LG'),
                    fontSize: fontSize('SM')
                  }}
                >
                  {t('common:vaultEditor.exportJson')}
                </Button>
              </Space>
            </div>
          ] : []),
          // Right side buttons
          <Button 
            key="cancel" 
            data-testid="resource-modal-cancel-button" 
            onClick={onCancel}
            style={{
              minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
              borderRadius: borderRadius('LG'),
              fontSize: fontSize('SM')
            }}
          >
            {t('general.cancel')}
          </Button>,
          ...(mode === 'create' && existingData && onUpdateVault ? [
            <Button 
              key="vault"
              data-testid="resource-modal-vault-button"
              onClick={() => setShowVaultModal(true)}
              style={{
                minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                borderRadius: borderRadius('LG'),
                fontSize: fontSize('SM')
              }}
            >
              {t('general.vault')}
            </Button>
          ] : []),
          ...(showFunctions ? [
            <Button 
              key="functions"
              data-testid="resource-modal-functions-button"
              onClick={() => setShowFunctionModal(true)}
              style={{
                minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                borderRadius: borderRadius('LG'),
                fontSize: fontSize('SM')
              }}
            >
              {t(`${resourceType}s.${resourceType}Functions`)}
            </Button>
          ] : []),
          <Button
            key="submit"
            data-testid="resource-modal-ok-button"
            type="primary"
            loading={isSubmitting}
            disabled={mode === 'create' && resourceType === 'machine' && !testConnectionSuccess}
            onClick={() => {
              if (formRef.current) {
                formRef.current.submit()
              }
            }}
            style={{ 
              ...styles.buttonPrimary,
              background: 'var(--color-primary)', 
              borderColor: 'var(--color-primary)',
              minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE
            }}
          >
            {mode === 'create' ? t('general.create') : t('general.save')}
          </Button>
        ]}
        className={ModalSize.ExtraLarge}
      >
        {/* Auto-setup checkbox for machine creation */}
        {resourceType === 'machine' && mode === 'create' && (
          <div style={{ marginBottom: spacing('MD') }}>
            <Checkbox 
              data-testid="resource-modal-auto-setup-checkbox"
              checked={autoSetupEnabled} 
              onChange={(e) => setAutoSetupEnabled(e.target.checked)}
              style={{
                fontSize: fontSize('SM'),
                minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                alignItems: 'center'
              }}
            >
              {t('machines:autoSetupAfterCreation')}
            </Checkbox>
          </div>
        )}
        
        {/* Keep open checkbox for repository creation - only show when creating physical storage (not credential-only mode) */}
        {resourceType === 'repository' && mode === 'create' && !((existingData?.repositoryGuid && existingData?.repositoryGuid.trim() !== '') || creationContext === 'credentials-only') && (
          <div style={{ marginBottom: spacing('MD') }}>
            <Checkbox 
              data-testid="resource-modal-keep-open-checkbox"
              checked={keepRepositoryOpen} 
              onChange={(e) => setKeepRepositoryOpen(e.target.checked)}
              style={{
                fontSize: fontSize('SM'),
                minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
                alignItems: 'center'
              }}
            >
              {t('resources:repositories.keepOpenAfterCreation')}
            </Checkbox>
          </div>
        )}
        
        <ResourceFormWithVault
          ref={formRef}
          form={form}
          fields={getFormFields()}
          onSubmit={handleSubmit}
          entityType={getEntityType()}
          vaultFieldName={getVaultFieldName()}
          showDefaultsAlert={mode === 'create' && uiMode === 'simple'}
          creationContext={creationContext}
          initialVaultData={(() => {
            if (existingData?.vaultContent) {
              try {
                let parsed = JSON.parse(existingData.vaultContent);
                console.log('[UnifiedResourceModal] Resource type:', resourceType);
                console.log('[UnifiedResourceModal] Existing data:', existingData);
                console.log('[UnifiedResourceModal] Raw vault content:', existingData.vaultContent);
                console.log('[UnifiedResourceModal] Parsed vault data for edit:', parsed);
                console.log('[UnifiedResourceModal] Parsed vault keys:', Object.keys(parsed));
                // Special handling for repositories - map the vault data correctly
                if (resourceType === 'repository') {
                  console.log('[UnifiedResourceModal] Repository vault before mapping:', JSON.stringify(parsed, null, 2));
                  // The vault data might have the credential at root level or nested
                  // We need to ensure it's in the format VaultEditor expects
                  if (!parsed.credential && parsed.repoVault) {
                    // If repoVault exists, it might contain the credential
                    try {
                      const innerVault = typeof parsed.repoVault === 'string' ?
                        JSON.parse(parsed.repoVault) : parsed.repoVault;
                      if (innerVault.credential) {
                        parsed = { credential: innerVault.credential };
                      }
                    } catch (e) {
                      console.error('[UnifiedResourceModal] Failed to parse inner vault:', e);
                    }
                  } else if (parsed.repositoryVault) {
                    // Or it might be in repositoryVault
                    try {
                      const innerVault = typeof parsed.repositoryVault === 'string' ?
                        JSON.parse(parsed.repositoryVault) : parsed.repositoryVault;
                      if (innerVault.credential) {
                        parsed = { credential: innerVault.credential };
                      }
                    } catch (e) {
                      console.error('[UnifiedResourceModal] Failed to parse repository vault:', e);
                    }
                  }
                  // If still no credential field but we have other fields, check if any could be the credential
                  if (!parsed.credential) {
                    // Check for any 32-character string that might be the credential
                    for (const [key, value] of Object.entries(parsed)) {
                      if (typeof value === 'string' && value.length === 32 &&
                          /^[A-Za-z0-9!@#$%^&*()_+{}|:<>,.?/]+$/.test(value)) {
                        console.log(`[UnifiedResourceModal] Found potential credential in field '${key}':`, value);
                        parsed = { credential: value };
                        break;
                      }
                    }
                  }
                  console.log('[UnifiedResourceModal] Repository vault after mapping:', JSON.stringify(parsed, null, 2));
                }
                return parsed;
              } catch (e) {
                console.error('[UnifiedResourceModal] Failed to parse vault content:', e);
                return {};
              }
            }
            return {};
          })()}
          hideImportExport={true}
          isEditMode={mode === 'edit'}
          onImportExportRef={(handlers) => {
            importExportHandlers.current = handlers
          }}
          teamName={form.getValues('teamName') || (existingData?.teamName) || (Array.isArray(teamFilter) ? teamFilter[0] : teamFilter) || 'Private Team'}
          bridgeName={form.getValues('bridgeName') || 'Global Bridges'}
          onTestConnectionStateChange={setTestConnectionSuccess}
          isModalOpen={open}
          beforeVaultContent={
            resourceType === 'repository' && mode === 'create' && !((existingData?.repositoryGuid && existingData?.repositoryGuid.trim() !== '') || creationContext === 'credentials-only') ? (
              <Collapse
                data-testid="resource-modal-template-collapse"
                style={{ marginBottom: 16, marginTop: 16 }}
                items={[
                  {
                    key: 'template',
                    label: (
                      <Space>
                        <AppstoreOutlined />
                        <Text>{t('resources:templates.selectTemplate')}</Text>
                        {selectedTemplate && (
                          <Tag color="blue">{selectedTemplate.replace(/^(db_|kick_|route_)/, '')}</Tag>
                        )}
                      </Space>
                    ),
                    children: (
                      <TemplateSelector
                        value={selectedTemplate}
                        onChange={setSelectedTemplate}
                        onViewDetails={(templateName) => {
                          setTemplateToView(templateName)
                          setShowTemplateDetails(true)
                        }}
                      />
                    )
                  }
                ]}
              />
            ) : undefined
          }
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
          showMachineSelection={resourceType === 'repository' || resourceType === 'storage'}
          teamName={existingData?.teamName}
          machines={dropdownData?.machinesByTeam?.find(t => t.teamName === existingData?.teamName)?.machines || []}
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
          preselectedFunction={preselectedFunction}
        />
      )}

      {/* Template Details Modal */}
      <TemplateDetailsModal
        visible={showTemplateDetails}
        templateName={templateToView}
        onClose={() => {
          setShowTemplateDetails(false)
          setTemplateToView(null)
        }}
        onUseTemplate={(templateName) => {
          setSelectedTemplate(templateName)
          setShowTemplateDetails(false)
          setTemplateToView(null)
        }}
      />
    </>
  )
}

export default UnifiedResourceModal