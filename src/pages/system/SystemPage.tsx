import React, { useState, useEffect, useRef } from 'react'
import { Card, Tabs, Modal, Form, Input, Button, Space, Popconfirm, Tag, Select, Badge, List, Typography, Row, Col, Table, Empty, Spin, Alert, message, Checkbox, Result, Radio, Upload } from 'antd'
import { 
  UserOutlined, 
  SafetyOutlined, 
  PlusOutlined, 
  DeleteOutlined,
  KeyOutlined,
  CheckCircleOutlined,
  StopOutlined,
  SettingOutlined,
  BankOutlined,
  EnvironmentOutlined,
  ApiOutlined,
  EditOutlined,
  DesktopOutlined,
  TeamOutlined,
  DatabaseOutlined,
  ScheduleOutlined,
  CloudServerOutlined,
  CopyOutlined,
  SyncOutlined,
  HistoryOutlined,
  WarningOutlined,
  DownloadOutlined,
  LockOutlined,
  UnlockOutlined,
  SafetyCertificateOutlined,
  UploadOutlined,
  ExportOutlined,
  ImportOutlined
} from '@/utils/optimizedIcons'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useSelector } from 'react-redux'
import { RootState } from '@/store/store'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { logout } from '@/store/auth/authSlice'
import { encryptString, decryptString } from '@/utils/encryption'
import { useDispatch } from 'react-redux'
import ResourceListView from '@/components/common/ResourceListView'
import { masterPasswordService } from '@/services/masterPasswordService'
import ResourceForm from '@/components/forms/ResourceForm'
import ResourceFormWithVault, { ResourceFormWithVaultRef } from '@/components/forms/ResourceFormWithVault'
import VaultEditorModal from '@/components/common/VaultEditorModal'
import AuditTraceModal from '@/components/common/AuditTraceModal'
import UnifiedResourceModal, { ResourceType } from '@/components/common/UnifiedResourceModal'
import UserSessionsTab from '@/components/system/UserSessionsTab'
import TwoFactorSettings from '@/components/settings/TwoFactorSettings'
import { useDropdownData } from '@/api/queries/useDropdownData'
import { 
  useUpdateCompanyVault, 
  useCompanyVault,
  useUpdateCompanyBlockUserRequests,
  useGetCompanyVaults,
  useUpdateCompanyVaults,
  useExportCompanyData,
  useImportCompanyData
} from '@/api/queries/company'
import { showMessage } from '@/utils/messages'

// User queries
import { 
  useUsers, 
  useCreateUser, 
  useDeactivateUser, 
  useAssignUserPermissions,
  useUpdateUserPassword, 
  User 
} from '@/api/queries/users'

// Permission queries
import { 
  usePermissionGroups as usePermissionGroupsQuery, 
  usePermissionGroupDetails,
  useCreatePermissionGroup, 
  useDeletePermissionGroup,
  useAddPermissionToGroup,
  useRemovePermissionFromGroup,
  useAssignUserToGroup,
  PermissionGroup 
} from '@/api/queries/permissions'
import { usePermissionGroups } from '@/api/queries/users'

// Region queries
import { 
  useRegions, 
  useCreateRegion, 
  useUpdateRegionName,
  useDeleteRegion, 
  useUpdateRegionVault, 
  Region 
} from '@/api/queries/regions'

// Bridge queries
import { 
  useBridges, 
  useCreateBridge, 
  useUpdateBridgeName,
  useDeleteBridge, 
  useUpdateBridgeVault,
  useResetBridgeAuthorization,
  Bridge 
} from '@/api/queries/bridges'

// Team queries
import {
  useTeams,
  useTeamMembers,
  useCreateTeam,
  useUpdateTeamName,
  useDeleteTeam,
  useUpdateTeamVault,
  useAddTeamMember,
  useRemoveTeamMember,
  Team,
  TeamMember
} from '@/api/queries/teams'

import { 
  createUserSchema, 
  CreateUserForm
} from '@/utils/validation'

const { Title, Text } = Typography

const SystemPage: React.FC = () => {
  const { t } = useTranslation('settings')
  const { t: tSystem } = useTranslation('system')
  const { t: tOrg } = useTranslation('resources')
  const { t: tCommon } = useTranslation('common')
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)
  const [currentMasterPassword, setCurrentMasterPassword] = useState<string | null>(null)
  const currentUser = useSelector((state: RootState) => state.auth.user)
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('users')
  
  // Load master password from secure storage on mount
  useEffect(() => {
    const loadMasterPassword = async () => {
      const password = await masterPasswordService.getMasterPassword()
      setCurrentMasterPassword(password)
    }
    loadMasterPassword()
  }, [])
  
  // Form refs
  const userFormRef = React.useRef<ResourceFormWithVaultRef>(null)
  
  // Set initial tab to users
  React.useEffect(() => {
    setActiveTab('users')
  }, [uiMode])
  
  // Settings state
  const [companyVaultModalOpen, setCompanyVaultModalOpen] = useState(false)
  const [userVaultModalOpen, setUserVaultModalOpen] = useState(false)
  const [changePasswordModalOpen, setChangePasswordModalOpen] = useState(false)
  const [twoFactorModalOpen, setTwoFactorModalOpen] = useState(false)
  const [changePasswordForm] = Form.useForm()
  
  // User state
  const [isCreateUserModalOpen, setIsCreateUserModalOpen] = useState(false)
  const [assignPermissionModal, setAssignPermissionModal] = useState<{
    open: boolean
    user?: User
  }>({ open: false })
  const [selectedUserGroup, setSelectedUserGroup] = useState<string>('')

  // Permission state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isManageModalOpen, setIsManageModalOpen] = useState(false)
  const [isAssignModalOpen, setIsAssignModalOpen] = useState(false)
  const [selectedGroup, setSelectedGroup] = useState<PermissionGroup | null>(null)
  const [newGroupName, setNewGroupName] = useState('')
  const [selectedPermission, setSelectedPermission] = useState<string>('')
  const [selectedUser, setSelectedUser] = useState<string>('')

  const [isManageTeamModalOpen, setIsManageTeamModalOpen] = useState(false)
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null)
  const [selectedMemberEmail, setSelectedMemberEmail] = useState<string>('')
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null)
  const [bridgeCredentialsModal, setBridgeCredentialsModal] = useState<{
    open: boolean
    bridge?: Bridge
  }>({ open: false })
  const [resetAuthModal, setResetAuthModal] = useState<{
    open: boolean
    bridgeName: string
    isCloudManaged: boolean
  }>({ open: false, bridgeName: '', isCloudManaged: false })

  // Audit trace modal state
  const [auditTraceModal, setAuditTraceModal] = useState<{
    open: boolean
    entityType: string | null
    entityIdentifier: string | null
    entityName?: string
  }>({ open: false, entityType: null, entityIdentifier: null })

  // Unified modal state
  const [unifiedModalState, setUnifiedModalState] = useState<{
    open: boolean
    resourceType: ResourceType
    mode: 'create' | 'edit' | 'vault'
    data?: any
  }>({ open: false, resourceType: 'team', mode: 'create' })
  const [currentResource, setCurrentResource] = useState<any>(null)

  // Danger zone state
  const [masterPasswordModalOpen, setMasterPasswordModalOpen] = useState(false)
  const [masterPasswordForm] = Form.useForm()
  // Set default operation based on whether a master password exists
  const defaultOperation = currentMasterPassword ? 'update' : 'create'
  const [masterPasswordOperation, setMasterPasswordOperation] = useState<'create' | 'update' | 'remove'>(defaultOperation)
  const [completedOperation, setCompletedOperation] = useState<'create' | 'update' | 'remove'>('update')
  const [successModalOpen, setSuccessModalOpen] = useState(false)
  const [countdown, setCountdown] = useState(60)
  const countdownInterval = useRef<NodeJS.Timeout | null>(null)
  
  // Data import/export state
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importMode, setImportMode] = useState<'skip' | 'override'>('skip')
  const [importForm] = Form.useForm()

  // Common hooks
  const { data: dropdownData } = useDropdownData()
  
  // Settings hooks
  const { data: companyVault } = useCompanyVault()
  const updateVaultMutation = useUpdateCompanyVault()
  
  // Danger zone hooks
  const blockUserRequestsMutation = useUpdateCompanyBlockUserRequests()
  const exportVaultsQuery = useGetCompanyVaults()
  const updateVaultsMutation = useUpdateCompanyVaults()
  const exportCompanyDataQuery = useExportCompanyData()
  const importCompanyDataMutation = useImportCompanyData()
  
  // User hooks
  const { data: users = [], isLoading: usersLoading } = useUsers()
  const createUserMutation = useCreateUser()
  const deactivateUserMutation = useDeactivateUser()
  const assignUserPermissionsMutation = useAssignUserPermissions()
  const updateUserPasswordMutation = useUpdateUserPassword()

  // Permission hooks
  const { data: permissionGroups = [], isLoading: permissionsLoading } = usePermissionGroupsQuery()
  const { data: groupDetails } = usePermissionGroupDetails(selectedGroup?.permissionGroupName || '')
  const createGroupMutation = useCreatePermissionGroup()
  const deleteGroupMutation = useDeletePermissionGroup()
  const addPermissionMutation = useAddPermissionToGroup()
  const removePermissionMutation = useRemovePermissionFromGroup()
  const assignUserMutation = useAssignUserToGroup()

  // Team hooks
  const { data: teams = [], isLoading: teamsLoading } = useTeams()
  const { data: teamMembers = [] } = useTeamMembers(selectedTeam?.teamName || '')
  const createTeamMutation = useCreateTeam()
  const updateTeamNameMutation = useUpdateTeamName()
  const deleteTeamMutation = useDeleteTeam()
  const updateTeamVaultMutation = useUpdateTeamVault()
  const addTeamMemberMutation = useAddTeamMember()
  const removeTeamMemberMutation = useRemoveTeamMember()

  // Region hooks - always fetch regions since they're always visible at the bottom
  const { data: regions, isLoading: regionsLoading } = useRegions(true)
  const regionsList: Region[] = regions || []
  const createRegionMutation = useCreateRegion()
  const updateRegionNameMutation = useUpdateRegionName()
  const deleteRegionMutation = useDeleteRegion()
  const updateRegionVaultMutation = useUpdateRegionVault()

  // Bridge hooks - fetch when a region is selected
  const { data: bridges, isLoading: bridgesLoading } = useBridges(selectedRegion || undefined)
  const bridgesList: Bridge[] = bridges || []
  const createBridgeMutation = useCreateBridge()
  const updateBridgeNameMutation = useUpdateBridgeName()
  const deleteBridgeMutation = useDeleteBridge()
  const updateBridgeVaultMutation = useUpdateBridgeVault()
  const resetBridgeAuthMutation = useResetBridgeAuthorization()

  // Auto-select first region when regions are loaded
  useEffect(() => {
    if (regionsList.length > 0 && !selectedRegion) {
      setSelectedRegion(regionsList[0].regionName)
    }
  }, [regionsList, selectedRegion])

  // Update default operation when modal opens
  useEffect(() => {
    if (masterPasswordModalOpen) {
      const newDefaultOperation = currentMasterPassword ? 'update' : 'create'
      setMasterPasswordOperation(newDefaultOperation)
    }
  }, [masterPasswordModalOpen, currentMasterPassword])

  // Countdown effect
  useEffect(() => {
    if (successModalOpen && countdown > 0) {
      countdownInterval.current = setInterval(() => {
        setCountdown((prev) => prev - 1)
      }, 1000)
    } else if (countdown === 0) {
      // Logout and redirect
      dispatch(logout())
      navigate('/login')
    }

    return () => {
      if (countdownInterval.current) {
        clearInterval(countdownInterval.current)
      }
    }
  }, [successModalOpen, countdown, dispatch, navigate])

  // User form
  const userForm = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      newUserEmail: '',
      newUserPassword: '',
    },
  })

  // Settings handlers
  const handleUpdateCompanyVault = async (vault: string, version: number) => {
    await updateVaultMutation.mutateAsync({
      companyVault: vault,
      vaultVersion: version,
    })
    setCompanyVaultModalOpen(false)
  }

  const handleUpdateUserVault = async (vault: string, version: number) => {
    // TODO: Implement user vault update when API is available
    // User vault update: vault, version
    setUserVaultModalOpen(false)
  }

  const handleChangePassword = async (values: { currentPassword: string; newPassword: string; confirmPassword: string }) => {
    if (!currentUser?.email) return

    try {
      await updateUserPasswordMutation.mutateAsync({
        userEmail: currentUser.email,
        newPassword: values.newPassword,
      })
      
      setChangePasswordModalOpen(false)
      changePasswordForm.resetFields()
      
      // Show success message with countdown
      let countdown = 3
      const modal = Modal.success({
        title: 'Password Changed Successfully',
        content: `Your password has been changed. You will be logged out in ${countdown} seconds...`,
        okText: 'Logout Now',
        onOk: () => {
          dispatch(logout())
          navigate('/login')
        },
      })
      
      const timer = setInterval(() => {
        countdown--
        modal.update({
          content: `Your password has been changed. You will be logged out in ${countdown} seconds...`,
        })
        
        if (countdown === 0) {
          clearInterval(timer)
          modal.destroy()
          dispatch(logout())
          navigate('/login')
        }
      }, 1000)
    } catch (error) {
      // Error handled by mutation
    }
  }

  // User handlers
  const handleCreateUser = async (data: CreateUserForm) => {
    try {
      await createUserMutation.mutateAsync({
        email: data.newUserEmail,
        password: data.newUserPassword,
      })
      setIsCreateUserModalOpen(false)
      userForm.reset()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeactivateUser = async (userEmail: string) => {
    try {
      await deactivateUserMutation.mutateAsync(userEmail)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleAssignUserPermissions = async () => {
    if (!assignPermissionModal.user || !selectedUserGroup) return

    try {
      await assignUserPermissionsMutation.mutateAsync({
        userEmail: assignPermissionModal.user.userEmail,
        permissionGroupName: selectedUserGroup,
      })
      setAssignPermissionModal({ open: false })
      setSelectedUserGroup('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Danger zone handlers
  const handleExportCompanyData = async () => {
    try {
      const result = await exportCompanyDataQuery.refetch()
      if (result.data) {
        // Create a timestamp for the filename
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0]
        
        // The export data should contain the full company export in JSON format
        const exportData = result.data
        
        // Create and download the file
        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `company-data-export-${timestamp}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        
        showMessage('success', tSystem('dangerZone.exportData.success'))
      }
    } catch (error) {
      showMessage('error', tSystem('dangerZone.exportData.error'))
    }
  }

  const handleImportCompanyData = async (values: any) => {
    if (!importFile) {
      showMessage('error', tSystem('dangerZone.importData.modal.fileRequired'))
      return
    }

    try {
      // Read the file content
      const fileContent = await importFile.text()
      
      // Validate JSON
      try {
        JSON.parse(fileContent)
      } catch {
        showMessage('error', tSystem('dangerZone.importData.modal.invalidFile'))
        return
      }

      // Import the data
      await importCompanyDataMutation.mutateAsync({
        companyDataJson: fileContent,
        importMode: importMode
      })

      setImportModalOpen(false)
      setImportFile(null)
      importForm.resetFields()
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleExportVaults = async () => {
    try {
      const result = await exportVaultsQuery.refetch()
      if (result.data) {
        // Create a timestamp for the filename
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0]
        
        // Dynamically build export data, excluding special fields
        const { allVaults, bridgesWithRequestCredential, ...vaultsByType } = result.data
        
        const exportData = {
          exportDate: new Date().toISOString(),
          vaults: vaultsByType,
          bridgesWithRequestCredential: bridgesWithRequestCredential,
          metadata: {
            totalVaults: allVaults.length,
            vaultTypes: Object.keys(vaultsByType).map(type => ({
              type,
              count: (vaultsByType as any)[type]?.length || 0
            }))
          }
        }
        
        // Create and download the file
        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `company-vaults-export-${timestamp}.json`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
        
        showMessage('success', tSystem('dangerZone.exportVaults.success'))
      }
    } catch (error) {
      // Failed to export vaults
      showMessage('error', tSystem('dangerZone.exportVaults.error'))
    }
  }

  const handleUpdateMasterPassword = async (values: { password?: string; confirmPassword?: string }) => {
    // Prevent duplicate submissions
    if (updateVaultsMutation.isPending) {
      return
    }

    try {
      // First, fetch all current vaults
      const vaultsResult = await exportVaultsQuery.refetch()
      if (!vaultsResult.data || !vaultsResult.data.allVaults) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.fetchVaults'))
        return
      }

      // Prepare vault updates using the allVaults array directly
      const vaultUpdates: any[] = []
      const newPassword = masterPasswordOperation === 'remove' ? '' : values.password!

      // Process all vaults from the allVaults array
      for (const vault of vaultsResult.data.allVaults) {
        if (vault.decryptedVault && vault.credential && vault.vaultName) {
          try {
            let vaultContent = vault.decryptedVault
            
            // Try to decrypt if it's client-encrypted (has current master password)
            if (currentMasterPassword && masterPasswordOperation !== 'create') {
              try {
                // Check if it looks like base64 encrypted data
                if (vaultContent.match(/^[A-Za-z0-9+/]+=*$/)) {
                  vaultContent = await decryptString(vaultContent, currentMasterPassword)
                }
              } catch (decryptError) {
                // If decryption fails, assume it's not encrypted
              }
            }
            
            // Handle based on operation type
            let finalContent = vaultContent
            if (masterPasswordOperation === 'remove') {
              // For remove operation, we just use the decrypted content
              finalContent = vaultContent
            } else {
              // For create and update operations, encrypt with the new password
              finalContent = await encryptString(vaultContent, newPassword)
            }
            
            vaultUpdates.push({
              credential: vault.credential,
              name: vault.vaultName,
              content: finalContent,
              version: vault.version || 1
            })
          } catch (error) {
            // Failed to process vault
            showMessage('error', `Failed to process vault ${vault.vaultName}`)
          }
        }
      }

      if (vaultUpdates.length === 0) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.noVaults'))
        return
      }

      // No need to show confirmation count since it's handled by mutations

      // Update all vaults
      await updateVaultsMutation.mutateAsync(vaultUpdates)
      
      // Unblock user requests after successful vault update
      await blockUserRequestsMutation.mutateAsync(false)
      
      // Update the master password in secure storage
      await masterPasswordService.setMasterPassword(masterPasswordOperation === 'remove' ? null : newPassword)
      setCurrentMasterPassword(masterPasswordOperation === 'remove' ? null : newPassword)
      
      setMasterPasswordModalOpen(false)
      masterPasswordForm.resetFields()
      setCompletedOperation(masterPasswordOperation) // Store completed operation
      setMasterPasswordOperation(defaultOperation) // Reset to default
      
      // Show success modal with countdown
      setCountdown(60)
      setSuccessModalOpen(true)
    } catch (error) {
      // Failed to update master password
      // Don't show error toast here as the mutation already handles it
    }
  }

  // Permission handlers
  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      showMessage('error', 'Please enter a group name')
      return
    }

    try {
      await createGroupMutation.mutateAsync({ permissionGroupName: newGroupName })
      setIsCreateModalOpen(false)
      setNewGroupName('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleDeleteGroup = async (groupName: string) => {
    try {
      await deleteGroupMutation.mutateAsync(groupName)
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleAddPermission = async () => {
    if (!selectedGroup || !selectedPermission) return

    try {
      await addPermissionMutation.mutateAsync({
        permissionGroupName: selectedGroup.permissionGroupName,
        permissionName: selectedPermission,
      })
      setSelectedPermission('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleRemovePermission = async (permission: string) => {
    if (!selectedGroup) return

    try {
      await removePermissionMutation.mutateAsync({
        permissionGroupName: selectedGroup.permissionGroupName,
        permissionName: permission,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleAssignUser = async () => {
    if (!selectedGroup || !selectedUser) return

    try {
      await assignUserMutation.mutateAsync({
        userEmail: selectedUser,
        permissionGroupName: selectedGroup.permissionGroupName,
      })
      setIsAssignModalOpen(false)
      setSelectedUser('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Team handlers


  const handleDeleteTeam = async (teamName: string) => {
    try {
      await deleteTeamMutation.mutateAsync(teamName)
    } catch (error) {
      // Error handled by mutation
    }
  }


  const handleAddTeamMember = async () => {
    if (!selectedTeam || !selectedMemberEmail) return

    try {
      await addTeamMemberMutation.mutateAsync({
        teamName: selectedTeam.teamName,
        newUserEmail: selectedMemberEmail,
      })
      setSelectedMemberEmail('')
    } catch (error) {
      // Error handled by mutation
    }
  }

  const handleRemoveTeamMember = async (userEmail: string) => {
    if (!selectedTeam) return

    try {
      await removeTeamMemberMutation.mutateAsync({
        teamName: selectedTeam.teamName,
        removeUserEmail: userEmail,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Region handlers


  const handleDeleteRegion = async (regionName: string) => {
    try {
      await deleteRegionMutation.mutateAsync(regionName)
      if (selectedRegion === regionName) {
        setSelectedRegion(null)
      }
    } catch (error) {
      // Error handled by mutation
    }
  }


  // Bridge handlers


  const handleDeleteBridge = async (bridge: Bridge) => {
    try {
      await deleteBridgeMutation.mutateAsync({
        regionName: bridge.regionName,
        bridgeName: bridge.bridgeName,
      })
    } catch (error) {
      // Error handled by mutation
    }
  }


  const handleResetBridgeAuth = async () => {
    try {
      await resetBridgeAuthMutation.mutateAsync({ 
        bridgeName: resetAuthModal.bridgeName,
        isCloudManaged: resetAuthModal.isCloudManaged 
      })
      setResetAuthModal({ open: false, bridgeName: '', isCloudManaged: false })
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Unified modal helpers
  const openUnifiedModal = (resourceType: ResourceType, mode: 'create' | 'edit' | 'vault', data?: any) => {
    setUnifiedModalState({
      open: true,
      resourceType,
      mode,
      data
    })
    setCurrentResource(data)
  }

  const closeUnifiedModal = () => {
    setUnifiedModalState({
      open: false,
      resourceType: 'team',
      mode: 'create'
    })
    setCurrentResource(null)
  }

  // Unified modal submit handler
  const handleUnifiedModalSubmit = async (data: any) => {
    try {
      switch (unifiedModalState.resourceType) {
        case 'team':
          if (unifiedModalState.mode === 'create') {
            await createTeamMutation.mutateAsync(data)
          } else if (unifiedModalState.mode === 'edit') {
            if (data.teamName !== currentResource.teamName) {
              await updateTeamNameMutation.mutateAsync({
                currentTeamName: currentResource.teamName,
                newTeamName: data.teamName,
              })
            }
            // Update vault if changed
            const vaultData = data.teamVault
            if (vaultData && vaultData !== currentResource.vaultContent) {
              await updateTeamVaultMutation.mutateAsync({
                teamName: data.teamName || currentResource.teamName,
                teamVault: vaultData,
                vaultVersion: currentResource.vaultVersion + 1,
              })
            }
          }
          break
        case 'region':
          if (unifiedModalState.mode === 'create') {
            await createRegionMutation.mutateAsync(data)
          } else if (unifiedModalState.mode === 'edit') {
            if (data.regionName !== currentResource.regionName) {
              await updateRegionNameMutation.mutateAsync({
                currentRegionName: currentResource.regionName,
                newRegionName: data.regionName,
              })
            }
            // Update vault if changed
            const vaultData = data.regionVault
            if (vaultData && vaultData !== currentResource.vaultContent) {
              await updateRegionVaultMutation.mutateAsync({
                regionName: data.regionName || currentResource.regionName,
                regionVault: vaultData,
                vaultVersion: currentResource.vaultVersion + 1,
              })
            }
          }
          break
        case 'bridge':
          if (unifiedModalState.mode === 'create') {
            await createBridgeMutation.mutateAsync(data)
          } else if (unifiedModalState.mode === 'edit') {
            if (data.bridgeName !== currentResource.bridgeName) {
              await updateBridgeNameMutation.mutateAsync({
                regionName: currentResource.regionName,
                currentBridgeName: currentResource.bridgeName,
                newBridgeName: data.bridgeName,
              })
            }
            // Update vault if changed
            const vaultData = data.bridgeVault
            if (vaultData && vaultData !== currentResource.vaultContent) {
              await updateBridgeVaultMutation.mutateAsync({
                regionName: data.regionName || currentResource.regionName,
                bridgeName: data.bridgeName || currentResource.bridgeName,
                bridgeVault: vaultData,
                vaultVersion: currentResource.vaultVersion + 1,
              })
            }
          }
          break
      }
      closeUnifiedModal()
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Unified vault update handler
  const handleUnifiedVaultUpdate = async (vault: string, version: number) => {
    if (!currentResource) return

    try {
      switch (unifiedModalState.resourceType) {
        case 'team':
          await updateTeamVaultMutation.mutateAsync({
            teamName: currentResource.teamName,
            teamVault: vault,
            vaultVersion: version,
          })
          break
        case 'region':
          await updateRegionVaultMutation.mutateAsync({
            regionName: currentResource.regionName,
            regionVault: vault,
            vaultVersion: version,
          })
          break
        case 'bridge':
          await updateBridgeVaultMutation.mutateAsync({
            regionName: currentResource.regionName,
            bridgeName: currentResource.bridgeName,
            bridgeVault: vault,
            vaultVersion: version,
          })
          break
      }
    } catch (error) {
      // Error handled by mutation
    }
  }

  // Permission columns
  const permissionColumns = [
    {
      title: 'Group Name',
      dataIndex: 'permissionGroupName',
      key: 'permissionGroupName',
      render: (text: string) => (
        <Space>
          <SafetyOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Users',
      dataIndex: 'userCount',
      key: 'userCount',
      width: 100,
      render: (count: number) => (
        <Badge count={count} showZero>
          <UserOutlined style={{ fontSize: 16 }} />
        </Badge>
      ),
    },
    {
      title: 'Permissions',
      dataIndex: 'permissionCount',
      key: 'permissionCount',
      width: 120,
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: '#556b2f' }}>
          <KeyOutlined style={{ fontSize: 16 }} />
        </Badge>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 350,
      render: (_: any, record: PermissionGroup) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<KeyOutlined />}
            onClick={() => {
              setSelectedGroup(record)
              setIsManageModalOpen(true)
            }}
          >
            Permissions
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<UserOutlined />}
            onClick={() => {
              setSelectedGroup(record)
              setIsAssignModalOpen(true)
            }}
          >
            Assign User
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'Permissions',
                entityIdentifier: record.permissionGroupName,
                entityName: record.permissionGroupName
              })
            }}
          >
            Trace
          </Button>
          <Popconfirm
            title="Delete Permission Group"
            description={`Are you sure you want to delete group "${record.permissionGroupName}"?`}
            onConfirm={() => handleDeleteGroup(record.permissionGroupName)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="primary"
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={deleteGroupMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // User columns
  const userColumns = [
    {
      title: 'Email',
      dataIndex: 'userEmail',
      key: 'userEmail',
      render: (email: string) => (
        <Space>
          <UserOutlined style={{ color: '#556b2f' }} />
          <strong>{email}</strong>
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'activated',
      key: 'activated',
      width: 120,
      render: (activated: boolean) => (
        activated ? (
          <Tag icon={<CheckCircleOutlined />} color="success">Active</Tag>
        ) : (
          <Tag icon={<StopOutlined />} color="default">Inactive</Tag>
        )
      ),
    },
    {
      title: 'Permission Group',
      dataIndex: 'permissionGroupName',
      key: 'permissionGroupName',
      render: (group: string) => group ? (
        <Tag icon={<SafetyOutlined />} color="blue">{group}</Tag>
      ) : (
        <Tag color="default">No Group</Tag>
      ),
    },
    {
      title: 'Last Active',
      dataIndex: 'lastActive',
      key: 'lastActive',
      render: (date: string) => date ? new Date(date).toLocaleDateString() : 'Never',
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 300,
      render: (_: any, record: User) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<SafetyOutlined />}
            onClick={() => {
              setAssignPermissionModal({ open: true, user: record })
              setSelectedUserGroup(record.permissionGroupName || '')
            }}
          >
            Permissions
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'User',
                entityIdentifier: record.userEmail,
                entityName: record.userEmail
              })
            }}
          >
            Trace
          </Button>
          {record.activated && (
            <Popconfirm
              title="Deactivate User"
              description={`Are you sure you want to deactivate "${record.userEmail}"?`}
              onConfirm={() => handleDeactivateUser(record.userEmail)}
              okText="Yes"
              cancelText="No"
              okButtonProps={{ danger: true }}
            >
              <Button 
                type="primary"
                danger
                size="small"
                loading={deactivateUserMutation.isPending}
              >
                Deactivate
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  // Get available permissions from dropdown data
  const availablePermissions = dropdownData?.permissions || []

  // Team columns
  const teamColumns = [
    {
      title: 'Team Name',
      dataIndex: 'teamName',
      key: 'teamName',
      render: (text: string) => (
        <Space>
          <TeamOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: 'Members',
      dataIndex: 'memberCount',
      key: 'memberCount',
      width: 100,
      render: (count: number) => (
        <Badge count={count} showZero>
          <UserOutlined style={{ fontSize: 16 }} />
        </Badge>
      ),
    },
    {
      title: 'Machines',
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 100,
      render: (count: number) => (
        <Space>
          <DesktopOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: 'Repositories',
      dataIndex: 'repoCount',
      key: 'repoCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <DatabaseOutlined />
          <span>{count || 0}</span>
        </Space>
      ),
    },
    {
      title: 'Storage',
      dataIndex: 'storageCount',
      key: 'storageCount',
      width: 100,
      render: (count: number) => (
        <Space>
          <CloudServerOutlined />
          <span>{count || 0}</span>
        </Space>
      ),
    },
    {
      title: 'Schedules',
      dataIndex: 'scheduleCount',
      key: 'scheduleCount',
      width: 100,
      render: (count: number) => (
        <Space>
          <ScheduleOutlined />
          <span>{count || 0}</span>
        </Space>
      ),
    },
    ...(uiMode === 'expert' ? [{
      title: 'Vault Version',
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: 'Actions',
      key: 'actions',
      width: 350,
      render: (_: any, record: Team) => (
        <Space>
          <Button 
            type="primary" 
            size="small"
            icon={<EditOutlined />}
            onClick={() => openUnifiedModal('team', 'edit', record)}
          >
            Edit
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<UserOutlined />}
            onClick={() => {
              setSelectedTeam(record)
              setIsManageTeamModalOpen(true)
            }}
          >
            Members
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'Team',
                entityIdentifier: record.teamName,
                entityName: record.teamName
              })
            }}
          >
            Trace
          </Button>
          <Popconfirm
            title="Delete Team"
            description={`Are you sure you want to delete team "${record.teamName}"?`}
            onConfirm={() => handleDeleteTeam(record.teamName)}
            okText="Yes"
            cancelText="No"
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="primary" 
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={deleteTeamMutation.isPending}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Region columns
  const regionColumns = [
    {
      title: tOrg('regions.regionName'),
      dataIndex: 'regionName',
      key: 'regionName',
      render: (text: string) => (
        <Space>
          <EnvironmentOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
        </Space>
      ),
    },
    {
      title: tOrg('regions.bridges'),
      dataIndex: 'bridgeCount',
      key: 'bridgeCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <ApiOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    ...(uiMode === 'expert' ? [{
      title: tOrg('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: tOrg('general.actions'),
      key: 'actions',
      width: 300,
      render: (_: any, record: Region) => (
        <Space>
          <Button 
            type="primary" 
            size="small"
            icon={<EditOutlined />}
            onClick={() => openUnifiedModal('region', 'edit', record)}
          >
            {tOrg('general.edit')}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'Region',
                entityIdentifier: record.regionName,
                entityName: record.regionName
              })
            }}
          >
            Trace
          </Button>
          <Popconfirm
            title={tOrg('regions.deleteRegion')}
            description={tOrg('regions.confirmDelete', { regionName: record.regionName })}
            onConfirm={() => handleDeleteRegion(record.regionName)}
            okText={tOrg('general.yes')}
            cancelText={tOrg('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="primary" 
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={deleteRegionMutation.isPending}
            >
              {tOrg('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Bridge columns
  const bridgeColumns = [
    {
      title: tOrg('bridges.bridgeName'),
      dataIndex: 'bridgeName',
      key: 'bridgeName',
      render: (text: string, record: Bridge) => (
        <Space>
          <ApiOutlined style={{ color: '#556b2f' }} />
          <strong>{text}</strong>
          {(record.hasAccess as number) === 1 && (
            <Tag color="green" icon={<CheckCircleOutlined />}>
              Access
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: tOrg('teams.machines'),
      dataIndex: 'machineCount',
      key: 'machineCount',
      width: 120,
      render: (count: number) => (
        <Space>
          <DesktopOutlined />
          <span>{count}</span>
        </Space>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'isGlobalBridge',
      key: 'isGlobalBridge',
      width: 100,
      render: (isGlobal: boolean) => (
        isGlobal ? (
          <Tag color="purple" icon={<CloudServerOutlined />}>Global</Tag>
        ) : (
          <Tag color="blue" icon={<ApiOutlined />}>Regular</Tag>
        )
      ),
    },
    {
      title: 'Management',
      dataIndex: 'managementMode',
      key: 'managementMode',
      width: 120,
      render: (mode: string) => {
        if (!mode) return <Tag>Local</Tag>
        const color = mode === 'Cloud' ? 'green' : 'default'
        const icon = mode === 'Cloud' ? <CloudServerOutlined /> : <DesktopOutlined />
        return <Tag color={color} icon={icon}>{mode}</Tag>
      },
    },
    ...(uiMode === 'expert' ? [{
      title: tOrg('general.vaultVersion'),
      dataIndex: 'vaultVersion',
      key: 'vaultVersion',
      width: 120,
      render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
    }] : []),
    {
      title: tOrg('general.actions'),
      key: 'actions',
      width: 400,
      render: (_: any, record: Bridge) => (
        <Space>
          <Button 
            type="primary" 
            size="small"
            icon={<EditOutlined />}
            onClick={() => openUnifiedModal('bridge', 'edit', record)}
          >
            {tOrg('general.edit')}
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<KeyOutlined />}
            onClick={() => setBridgeCredentialsModal({ open: true, bridge: record })}
          >
            Token
          </Button>
          <Button 
            type="primary" 
            size="small"
            icon={<SyncOutlined />}
            onClick={() => setResetAuthModal({ 
              open: true, 
              bridgeName: record.bridgeName, 
              isCloudManaged: false 
            })}
          >
            Reset Auth
          </Button>
          <Button
            type="primary"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => {
              setAuditTraceModal({
                open: true,
                entityType: 'Bridge',
                entityIdentifier: record.bridgeName,
                entityName: record.bridgeName
              })
            }}
          >
            Trace
          </Button>
          <Popconfirm
            title={tOrg('bridges.deleteBridge')}
            description={tOrg('bridges.confirmDelete', { bridgeName: record.bridgeName })}
            onConfirm={() => handleDeleteBridge(record)}
            okText={tOrg('general.yes')}
            cancelText={tOrg('general.no')}
            okButtonProps={{ danger: true }}
          >
            <Button 
              type="primary" 
              danger
              size="small"
              icon={<DeleteOutlined />}
              loading={deleteBridgeMutation.isPending}
            >
              {tOrg('general.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const userFormFields = [
    {
      name: 'newUserEmail',
      label: 'Email',
      type: 'email' as const,
      placeholder: 'user@example.com',
      required: true,
    },
    {
      name: 'newUserPassword',
      label: 'Password',
      type: 'password' as const,
      placeholder: 'Enter password',
      required: true,
    },
  ]

  const teamFormFields = [
    {
      name: 'teamName',
      label: 'Team Name',
      placeholder: 'Enter team name',
      required: true,
    },
  ]

  // Form fields
  const regionFormFields = [
    {
      name: 'regionName',
      label: tOrg('regions.regionName'),
      placeholder: tOrg('regions.placeholders.enterRegionName'),
      required: true,
    },
  ]

  const bridgeFormFields = uiMode === 'simple'
    ? [
        {
          name: 'bridgeName',
          label: tOrg('bridges.bridgeName'),
          placeholder: tOrg('bridges.placeholders.enterBridgeName'),
          required: true,
        },
      ]
    : [
        {
          name: 'regionName',
          label: tOrg('general.region'),
          placeholder: tOrg('regions.placeholders.selectRegion'),
          required: true,
          type: 'select' as const,
          options: dropdownData?.regions?.map((r: any) => ({ value: r.value, label: r.label })) || [],
        },
        {
          name: 'bridgeName',
          label: tOrg('bridges.bridgeName'),
          placeholder: tOrg('bridges.placeholders.enterBridgeName'),
          required: true,
        },
      ]

  // Define tab configurations
  const usersTab = {
    key: 'users',
    label: (
      <span>
        <UserOutlined />
        Users
      </span>
    ),
    children: (
      <ResourceListView
        title={
          <Space>
            <span style={{ fontSize: 16, fontWeight: 500 }}>Users</span>
            <span style={{ fontSize: 14, color: '#666' }}>Manage users and their permissions</span>
          </Space>
        }
        loading={usersLoading}
        data={users}
        columns={userColumns}
        rowKey="userEmail"
        searchPlaceholder="Search users..."
        actions={
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => setIsCreateUserModalOpen(true)}
          >
            Create User
          </Button>
        }
      />
    ),
  }

  const permissionsTab = {
    key: 'permissions',
    label: (
      <span>
        <SafetyOutlined />
        Permissions
      </span>
    ),
    children: (
      <ResourceListView
        title={
          <Space>
            <span style={{ fontSize: 16, fontWeight: 500 }}>Permission Groups</span>
            <span style={{ fontSize: 14, color: '#666' }}>Manage permission groups and their assignments</span>
          </Space>
        }
        loading={permissionsLoading}
        data={permissionGroups}
        columns={permissionColumns}
        rowKey="permissionGroupName"
        searchPlaceholder="Search permission groups..."
        actions={
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalOpen(true)}
          >
            Create Group
          </Button>
        }
      />
    ),
  }

  const teamsTab = {
    key: 'teams',
    label: (
      <span>
        <TeamOutlined />
        Teams
      </span>
    ),
    children: (
      <ResourceListView
        title={
          <Space>
            <span style={{ fontSize: 16, fontWeight: 500 }}>Teams</span>
            <span style={{ fontSize: 14, color: '#666' }}>Manage teams and their members</span>
          </Space>
        }
        loading={teamsLoading}
        data={teams}
        columns={teamColumns}
        rowKey="teamName"
        searchPlaceholder="Search teams..."
        actions={
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => openUnifiedModal('team', 'create')}
          >
            Create Team
          </Button>
        }
      />
    ),
  }

  const userSessionsTab = {
    key: 'sessions',
    label: (
      <span>
        <DesktopOutlined />
        User Sessions
      </span>
    ),
    children: <UserSessionsTab />,
  }

  // Compose tabs based on UI mode
  const tabItems = uiMode === 'simple' 
    ? [usersTab, teamsTab]
    : [usersTab, teamsTab, permissionsTab, userSessionsTab]

  return (
    <>
      {/* Settings Section */}
      <Space direction="vertical" size={24} style={{ width: '100%', marginBottom: 24 }}>
        <Title level={3}>{t('title')}</Title>

        <Row gutter={[16, 16]}>
          {/* Company Settings Card */}
          <Col xs={24} lg={12}>
            <Card style={{ height: '100%' }}>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Space>
                  <BankOutlined style={{ fontSize: 24, color: '#556b2f' }} />
                  <Title level={4} style={{ margin: 0 }}>{t('company.title')}</Title>
                </Space>
                
                <Text type="secondary">
                  {t('company.description')}
                </Text>

                <Button
                  type="primary"
                  icon={<SettingOutlined />}
                  onClick={() => setCompanyVaultModalOpen(true)}
                  size="large"
                  style={{ marginTop: 16 }}
                >
                  {t('company.configureVault')}
                </Button>
              </Space>
            </Card>
          </Col>

          {/* User Settings Card */}
          <Col xs={24} lg={12}>
            <Card style={{ height: '100%' }}>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Space>
                  <UserOutlined style={{ fontSize: 24, color: '#556b2f' }} />
                  <Title level={4} style={{ margin: 0 }}>{t('personal.title')}</Title>
                </Space>
                
                <Text type="secondary">
                  {t('personal.description')}
                </Text>

                <Space style={{ marginTop: 16 }} wrap>
                  <Button
                    type="primary"
                    icon={<SettingOutlined />}
                    onClick={() => setUserVaultModalOpen(true)}
                    size="large"
                  >
                    {t('personal.configureVault')}
                  </Button>
                  <Button
                    type="primary"
                    icon={<KeyOutlined />}
                    onClick={() => setChangePasswordModalOpen(true)}
                    size="large"
                  >
                    Change Password
                  </Button>
                  <Button
                    type="primary"
                    icon={<SafetyCertificateOutlined />}
                    onClick={() => setTwoFactorModalOpen(true)}
                    size="large"
                  >
                    Two-Factor Authentication
                  </Button>
                </Space>
              </Space>
            </Card>
          </Col>
        </Row>
      </Space>

      {/* New Title Between Settings and Users */}
      <Title level={3} style={{ marginBottom: 24 }}>Users, Teams & Permissions</Title>

      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
        />
      </Card>

      {/* Permission Modals */}
      <Modal
        title="Create Permission Group"
        open={isCreateModalOpen}
        onCancel={() => {
          setIsCreateModalOpen(false)
          setNewGroupName('')
        }}
        onOk={handleCreateGroup}
        confirmLoading={createGroupMutation.isPending}
      >
        <Input
          placeholder="Enter group name"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          onPressEnter={handleCreateGroup}
          autoComplete="off"
        />
      </Modal>

      <Modal
        title={`Manage Permissions - ${selectedGroup?.permissionGroupName}`}
        open={isManageModalOpen}
        onCancel={() => {
          setIsManageModalOpen(false)
          setSelectedGroup(null)
          setSelectedPermission('')
        }}
        footer={null}
        width={800}
      >
        <Tabs
          items={[
            {
              key: 'current',
              label: 'Current Permissions',
              children: (
                <Card>
                  <List
                    dataSource={groupDetails?.permissions || []}
                    renderItem={(permission: string) => (
                      <List.Item
                        actions={[
                          <Button
                            key="remove"
                            type="primary"
                            danger
                            size="small"
                            onClick={() => handleRemovePermission(permission)}
                            loading={removePermissionMutation.isPending}
                          >
                            Remove
                          </Button>
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<KeyOutlined />}
                          title={permission}
                        />
                      </List.Item>
                    )}
                    locale={{ emptyText: 'No permissions assigned' }}
                  />
                </Card>
              ),
            },
            {
              key: 'add',
              label: 'Add Permissions',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size={16}>
                  <Space style={{ width: '100%' }}>
                    <Select
                      placeholder="Select permission to add"
                      style={{ width: 400 }}
                      value={selectedPermission}
                      onChange={setSelectedPermission}
                      showSearch
                      filterOption={(input, option) =>
                        String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                    >
                      {availablePermissions.map(perm => (
                        <Select.Option 
                          key={perm.name} 
                          value={perm.name}
                          label={perm.name}
                          disabled={groupDetails?.permissions?.includes(perm.name)}
                        >
                          {perm.name}
                        </Select.Option>
                      ))}
                    </Select>
                    <Button
                      type="primary"
                      onClick={handleAddPermission}
                      loading={addPermissionMutation.isPending}
                      disabled={!selectedPermission}
                    >
                      Add Permission
                    </Button>
                  </Space>
                </Space>
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title={`Assign User to ${selectedGroup?.permissionGroupName}`}
        open={isAssignModalOpen}
        onCancel={() => {
          setIsAssignModalOpen(false)
          setSelectedGroup(null)
          setSelectedUser('')
        }}
        onOk={handleAssignUser}
        confirmLoading={assignUserMutation.isPending}
      >
        <Select
          placeholder="Select user"
          style={{ width: '100%' }}
          value={selectedUser}
          onChange={setSelectedUser}
          showSearch
          filterOption={(input, option) =>
            (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
          }
          options={dropdownData?.users?.map(u => ({ 
            value: u.value, 
            label: u.label,
            disabled: u.status !== 'active'
          })) || []}
        />
      </Modal>

      {/* User Modals */}
      <Modal
        title="Create User"
        open={isCreateUserModalOpen}
        onCancel={() => {
          setIsCreateUserModalOpen(false)
          userForm.reset()
        }}
        footer={null}
      >
        <ResourceForm
          form={userForm}
          fields={userFormFields}
          onSubmit={handleCreateUser}
          submitText="Create"
          cancelText="Cancel"
          onCancel={() => {
            setIsCreateUserModalOpen(false)
            userForm.reset()
          }}
          loading={createUserMutation.isPending}
        />
      </Modal>

      <Modal
        title={`Assign Permissions - ${assignPermissionModal.user?.userEmail}`}
        open={assignPermissionModal.open}
        onCancel={() => {
          setAssignPermissionModal({ open: false })
          setSelectedUserGroup('')
        }}
        onOk={handleAssignUserPermissions}
        okText="Assign"
        confirmLoading={assignUserPermissionsMutation.isPending}
      >
        <Form layout="vertical">
          <Form.Item label="Permission Group">
            <Select
              value={selectedUserGroup}
              onChange={setSelectedUserGroup}
              placeholder="Select permission group"
              options={permissionGroups?.map(group => ({
                value: group.permissionGroupName,
                label: `${group.permissionGroupName} (${group.userCount} users, ${group.permissionCount} permissions)`,
              }))}
              allowClear
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Company Vault Modal */}
      <VaultEditorModal
        open={companyVaultModalOpen}
        onCancel={() => setCompanyVaultModalOpen(false)}
        onSave={handleUpdateCompanyVault}
        entityType="COMPANY"
        title={t('company.modalTitle')}
        initialVault={companyVault?.vault || '{}'}
        initialVersion={companyVault?.vaultVersion || 1}
        loading={updateVaultMutation.isPending}
      />

      {/* User Vault Modal */}
      <VaultEditorModal
        open={userVaultModalOpen}
        onCancel={() => setUserVaultModalOpen(false)}
        onSave={handleUpdateUserVault}
        entityType="USER"
        title={t('personal.modalTitle')}
        initialVault={'{}'}
        initialVersion={1}
        loading={false}
      />

      <Modal
        title={`Manage Team Members - ${selectedTeam?.teamName}`}
        open={isManageTeamModalOpen}
        onCancel={() => {
          setIsManageTeamModalOpen(false)
          setSelectedTeam(null)
          setSelectedMemberEmail('')
        }}
        footer={null}
        width={800}
      >
        <Tabs
          items={[
            {
              key: 'current',
              label: 'Current Members',
              children: (
                <Card>
                  <List
                    dataSource={teamMembers}
                    renderItem={(member: TeamMember) => (
                      <List.Item
                        actions={[
                          <Popconfirm
                            key="remove"
                            title="Remove Team Member"
                            description={`Are you sure you want to remove "${member.userEmail}" from this team?`}
                            onConfirm={() => handleRemoveTeamMember(member.userEmail)}
                            okText="Yes"
                            cancelText="No"
                            okButtonProps={{ danger: true }}
                          >
                            <Button
                              type="primary"
                              danger
                              size="small"
                              loading={removeTeamMemberMutation.isPending}
                            >
                              Remove
                            </Button>
                          </Popconfirm>
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<UserOutlined />}
                          title={member.userEmail}
                          description={
                            <Space size="small">
                              {member.isMember && <Tag color="green">Member</Tag>}
                              {member.hasAccess && <Tag color="blue">Has Access</Tag>}
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                    locale={{ emptyText: 'No members in this team' }}
                  />
                </Card>
              ),
            },
            {
              key: 'add',
              label: 'Add Members',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size={16}>
                  <Space style={{ width: '100%' }}>
                    <Select
                      placeholder="Select user to add"
                      style={{ width: 400 }}
                      value={selectedMemberEmail}
                      onChange={setSelectedMemberEmail}
                      showSearch
                      filterOption={(input, option) =>
                        String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                      options={dropdownData?.users?.filter(u => u.status === 'active')?.map(u => ({ 
                        value: u.value, 
                        label: u.label,
                        disabled: teamMembers.some((m: TeamMember) => m.userEmail === u.value && m.isMember)
                      })) || []}
                    />
                    <Button
                      type="primary"
                      onClick={handleAddTeamMember}
                      loading={addTeamMemberMutation.isPending}
                      disabled={!selectedMemberEmail}
                    >
                      Add Member
                    </Button>
                  </Space>
                </Space>
              ),
            },
          ]}
        />
      </Modal>



      {/* Regions & Infrastructure Section */}
      {uiMode === 'expert' && (
        <>
          <Title level={3} style={{ marginTop: 48, marginBottom: 24 }}>{tSystem('regionsInfrastructure.title')}</Title>
          
          <Card>
        <Row gutter={[24, 24]}>
          <Col span={24}>
            <ResourceListView
              title={
                <Space>
                  <span style={{ fontSize: 16, fontWeight: 500 }}>{tOrg('regions.title')}</span>
                  <span style={{ fontSize: 14, color: '#666' }}>{tOrg('regions.selectRegionPrompt')}</span>
                </Space>
              }
              loading={regionsLoading}
              data={regionsList}
              columns={regionColumns}
              rowKey="regionName"
              searchPlaceholder={tOrg('regions.searchRegions')}
              actions={
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={() => openUnifiedModal('region', 'create')}
                >
                  {tOrg('regions.createRegion')}
                </Button>
              }
              rowSelection={{
                type: 'radio',
                selectedRowKeys: selectedRegion ? [selectedRegion] : [],
                onChange: (selectedRowKeys: React.Key[]) => {
                  setSelectedRegion(selectedRowKeys[0] as string || null)
                },
              }}
              onRow={(record) => ({
                onClick: () => setSelectedRegion(record.regionName),
                className: selectedRegion === record.regionName ? 'selected-row' : '',
                style: { cursor: 'pointer' },
              })}
            />
          </Col>
          
          <Col span={24}>
            <Card>
              <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <Title level={4} style={{ margin: 0 }}>
                    {selectedRegion ? tOrg('regions.bridgesInRegion', { region: selectedRegion }) : tOrg('bridges.title')}
                  </Title>
                  {!selectedRegion && (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      {tOrg('regions.selectRegionToView')}
                    </Text>
                  )}
                </div>
                {selectedRegion && (
                  <Button 
                    type="primary" 
                    icon={<PlusOutlined />}
                    onClick={() => {
                      openUnifiedModal('bridge', 'create', { regionName: selectedRegion })
                    }}
                  >
                    {tOrg('bridges.createBridge')}
                  </Button>
                )}
              </div>
              
              {!selectedRegion ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={tOrg('regions.selectRegionPrompt')}
                  style={{ padding: '40px 0' }}
                />
              ) : bridgesLoading ? (
                <div style={{ textAlign: 'center', padding: '100px 0' }}>
                  <Spin size="large" tip={t('common:general.loading')} />
                </div>
              ) : (
                <Table
                  columns={bridgeColumns}
                  dataSource={bridgesList}
                  rowKey="bridgeName"
                  pagination={{
                    total: bridgesList.length || 0,
                    pageSize: 10,
                    showSizeChanger: true,
                    showTotal: (total) => tOrg('bridges.totalBridges', { total }),
                  }}
                  locale={{
                    emptyText: tOrg('bridges.noBridges'),
                  }}
                />
              )}
            </Card>
          </Col>
        </Row>
      </Card>
        </>
      )}

      <Modal
        title={`Bridge Token - ${bridgeCredentialsModal.bridge?.bridgeName || ''}`}
        open={bridgeCredentialsModal.open}
        onCancel={() => setBridgeCredentialsModal({ open: false })}
        footer={[
          <Button 
            key="close" 
            onClick={() => setBridgeCredentialsModal({ open: false })}
          >
            Close
          </Button>
        ]}
        width={600}
      >
        {(() => {
          const bridge = bridgeCredentialsModal.bridge
          if (!bridge) return null
          
          // Bridge credentials is the token directly
          const token = bridge.bridgeCredentials
          
          // Check if we have the necessary access
          if (bridge.hasAccess === 0) {
            return (
              <Alert
                message="Access Denied"
                description="You don't have the necessary permissions to view bridge credentials. Please contact an administrator."
                type="error"
                showIcon
              />
            )
          }
          
          if (!token) {
            return (
              <Alert
                message="No Bridge Token Available"
                description="Bridge credentials are not available. This could be because you don't have the necessary permissions, or the bridge credentials vault has not been created. Administrators can use 'Reset Auth' to generate new credentials."
                type="info"
                showIcon
              />
            )
          }
          
          return (
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <Alert
                message="Bridge Authentication Token"
                description="This token is used by the bridge to authenticate its first connection to the system. After the first successful use, the bridge will receive a new token for subsequent requests. If this token has already been used, you'll need to use 'Reset Auth' to generate new credentials."
                type="warning"
                showIcon
              />
              
              <div>
                <Text strong>Token:</Text>
                <Space.Compact style={{ marginTop: 8, width: '100%' }}>
                  <Input
                    value={token}
                    readOnly
                    style={{ width: '100%' }}
                    autoComplete="off"
                  />
                  <Button
                    icon={<CopyOutlined />}
                    onClick={() => {
                      navigator.clipboard.writeText(token)
                      message.success('Token copied to clipboard')
                    }}
                  />
                </Space.Compact>
              </div>
              
              <Alert
                message="Important"
                description="Keep this token secure. It provides access to process queue items on behalf of your organization. If you suspect the token has been compromised, use 'Reset Auth' immediately."
                type="info"
                showIcon
              />
            </Space>
          )
        })()}
      </Modal>

      {/* Audit Trace Modal */}
      <AuditTraceModal
        open={auditTraceModal.open}
        onCancel={() => setAuditTraceModal({ open: false, entityType: null, entityIdentifier: null })}
        entityType={auditTraceModal.entityType}
        entityIdentifier={auditTraceModal.entityIdentifier}
        entityName={auditTraceModal.entityName}
      />

      {/* Unified Resource Modal */}
      <UnifiedResourceModal
        open={unifiedModalState.open}
        onCancel={closeUnifiedModal}
        resourceType={unifiedModalState.resourceType}
        mode={unifiedModalState.mode}
        existingData={unifiedModalState.data || currentResource}
        onSubmit={handleUnifiedModalSubmit}
        onUpdateVault={unifiedModalState.mode === 'edit' ? handleUnifiedVaultUpdate : undefined}
        isSubmitting={
          createTeamMutation.isPending ||
          updateTeamNameMutation.isPending ||
          createRegionMutation.isPending ||
          updateRegionNameMutation.isPending ||
          createBridgeMutation.isPending ||
          updateBridgeNameMutation.isPending
        }
        isUpdatingVault={
          updateTeamVaultMutation.isPending ||
          updateRegionVaultMutation.isPending ||
          updateBridgeVaultMutation.isPending
        }
      />

      {/* Danger Zone Section */}
      {uiMode === 'expert' && (
        <>
          <Title level={3} style={{ marginTop: 48, marginBottom: 24, color: '#ff4d4f' }}>
            <WarningOutlined /> {tSystem('dangerZone.title')}
          </Title>
          
          <Card style={{ borderColor: '#ff4d4f' }}>
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          
          {/* Block/Unblock User Requests */}
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={16}>
              <Space direction="vertical" size={8}>
                <Title level={5} style={{ margin: 0 }}>{tSystem('dangerZone.blockUserRequests.title')}</Title>
                <Text type="secondary">
                  {tSystem('dangerZone.blockUserRequests.description')}
                </Text>
              </Space>
            </Col>
            <Col xs={24} lg={8} style={{ textAlign: 'right' }}>
              <Space>
                <Popconfirm
                  title={tSystem('dangerZone.blockUserRequests.confirmBlock.title')}
                  description={
                    <Space direction="vertical">
                      <Text>{tSystem('dangerZone.blockUserRequests.confirmBlock.description')}</Text>
                      <ul style={{ margin: '8px 0', paddingLeft: 20 }}>
                        <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect1')}</li>
                        <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect2')}</li>
                        <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect3')}</li>
                      </ul>
                      <Text strong>{tSystem('dangerZone.blockUserRequests.confirmBlock.confirm')}</Text>
                    </Space>
                  }
                  onConfirm={() => blockUserRequestsMutation.mutate(true)}
                  okText={tSystem('dangerZone.blockUserRequests.confirmBlock.okText')}
                  cancelText={tCommon('general.cancel')}
                  okButtonProps={{ danger: true }}
                >
                  <Button 
                    type="primary"
                    danger
                    icon={<LockOutlined />}
                    loading={blockUserRequestsMutation.isPending}
                  >
                    {tSystem('dangerZone.blockUserRequests.blockButton')}
                  </Button>
                </Popconfirm>
                <Popconfirm
                  title={tSystem('dangerZone.blockUserRequests.confirmUnblock.title')}
                  description={tSystem('dangerZone.blockUserRequests.confirmUnblock.description')}
                  onConfirm={() => blockUserRequestsMutation.mutate(false)}
                  okText={tSystem('dangerZone.blockUserRequests.confirmUnblock.okText')}
                  cancelText={tCommon('general.cancel')}
                >
                  <Button 
                    type="primary"
                    icon={<UnlockOutlined />}
                    loading={blockUserRequestsMutation.isPending}
                  >
                    {tSystem('dangerZone.blockUserRequests.unblockButton')}
                  </Button>
                </Popconfirm>
              </Space>
            </Col>
          </Row>

          <hr style={{ margin: 0, borderColor: '#f0f0f0' }} />

          {/* Export Company Vaults */}
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={16}>
              <Space direction="vertical" size={8}>
                <Title level={5} style={{ margin: 0 }}>{tSystem('dangerZone.exportVaults.title')}</Title>
                <Text type="secondary">
                  {tSystem('dangerZone.exportVaults.description')}
                </Text>
              </Space>
            </Col>
            <Col xs={24} lg={8} style={{ textAlign: 'right' }}>
              <Button 
                type="primary"
                icon={<DownloadOutlined />}
                onClick={handleExportVaults}
                loading={exportVaultsQuery.isFetching}
              >
                {tSystem('dangerZone.exportVaults.button')}
              </Button>
            </Col>
          </Row>

          <hr style={{ margin: 0, borderColor: '#f0f0f0' }} />

          {/* Export Company Data */}
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={16}>
              <Space direction="vertical" size={8}>
                <Title level={5} style={{ margin: 0 }}>{tSystem('dangerZone.exportData.title')}</Title>
                <Text type="secondary">
                  {tSystem('dangerZone.exportData.description')}
                </Text>
              </Space>
            </Col>
            <Col xs={24} lg={8} style={{ textAlign: 'right' }}>
              <Button 
                type="primary"
                icon={<ExportOutlined />}
                onClick={handleExportCompanyData}
                loading={exportCompanyDataQuery.isFetching}
              >
                {tSystem('dangerZone.exportData.button')}
              </Button>
            </Col>
          </Row>

          <hr style={{ margin: 0, borderColor: '#f0f0f0' }} />

          {/* Import Company Data */}
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={16}>
              <Space direction="vertical" size={8}>
                <Title level={5} style={{ margin: 0 }}>{tSystem('dangerZone.importData.title')}</Title>
                <Text type="secondary">
                  {tSystem('dangerZone.importData.description')}
                </Text>
              </Space>
            </Col>
            <Col xs={24} lg={8} style={{ textAlign: 'right' }}>
              <Button 
                type="primary"
                danger
                icon={<ImportOutlined />}
                onClick={() => setImportModalOpen(true)}
              >
                {tSystem('dangerZone.importData.button')}
              </Button>
            </Col>
          </Row>

          <hr style={{ margin: 0, borderColor: '#f0f0f0' }} />

          {/* Update Master Password */}
          <Row gutter={[16, 16]} align="middle">
            <Col xs={24} lg={16}>
              <Space direction="vertical" size={8}>
                <Title level={5} style={{ margin: 0 }}>{tSystem('dangerZone.updateMasterPassword.title')}</Title>
                <Text type="secondary">
                  {tSystem('dangerZone.updateMasterPassword.description')}
                </Text>
                <ul style={{ margin: '8px 0 0 20px', fontSize: 14, color: 'rgba(0, 0, 0, 0.45)' }}>
                  <li>{tSystem('dangerZone.updateMasterPassword.effect1')}</li>
                  <li>{tSystem('dangerZone.updateMasterPassword.effect2')}</li>
                  <li>{tSystem('dangerZone.updateMasterPassword.effect3')}</li>
                </ul>
                <Text type="secondary" strong style={{ display: 'block', marginTop: 8 }}>
                  {tSystem('dangerZone.updateMasterPassword.warning')}
                </Text>
              </Space>
            </Col>
            <Col xs={24} lg={8} style={{ textAlign: 'right' }}>
              <Button 
                type="primary"
                danger
                icon={<KeyOutlined />}
                onClick={() => setMasterPasswordModalOpen(true)}
              >
                {tSystem('dangerZone.updateMasterPassword.button')}
              </Button>
            </Col>
          </Row>

        </Space>
      </Card>
        </>
      )}

      {/* Master Password Update Modal */}
      <Modal
        title={currentMasterPassword ? tSystem('dangerZone.updateMasterPassword.modal.title') : tSystem('dangerZone.updateMasterPassword.modal.operationCreate')}
        open={masterPasswordModalOpen}
        onCancel={() => {
          setMasterPasswordModalOpen(false)
          masterPasswordForm.resetFields()
          setMasterPasswordOperation(defaultOperation)
        }}
        footer={null}
        width={600}
      >
        <Form
          layout="vertical"
          form={masterPasswordForm}
          onFinish={handleUpdateMasterPassword}
        >
          {/* Operation Type Selection - Only show when there are multiple options */}
          {currentMasterPassword && (
            <Form.Item
              label={tSystem('dangerZone.updateMasterPassword.modal.operationType')}
              style={{ marginBottom: 24 }}
            >
              <Radio.Group 
                value={masterPasswordOperation} 
                onChange={(e) => {
                  setMasterPasswordOperation(e.target.value)
                  masterPasswordForm.resetFields(['password', 'confirmPassword'])
                }}
              >
                <Space direction="vertical">
                  <Radio value="update">{tSystem('dangerZone.updateMasterPassword.modal.operationUpdate')}</Radio>
                  <Radio value="remove">{tSystem('dangerZone.updateMasterPassword.modal.operationRemove')}</Radio>
                </Space>
              </Radio.Group>
            </Form.Item>
          )}

          <Alert
            message={<>{'\u26A0\uFE0F'} {tSystem('dangerZone.updateMasterPassword.modal.warningTitle').replace('⚠️ ', '')}</>}
            description={
              <Space direction="vertical" size={8}>
                <Text>{tSystem(`dangerZone.updateMasterPassword.modal.warningDescription${masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)}`)}</Text>
                <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
                  <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect1')}</li>
                  <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect2')}</li>
                  <li>{tSystem(`dangerZone.updateMasterPassword.modal.warningEffect3${masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)}`)}</li>
                  {masterPasswordOperation !== 'remove' && (
                    <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect4')}</li>
                  )}
                </ul>
                <Text strong>{tSystem('dangerZone.updateMasterPassword.modal.warningPermanent')}</Text>
                <Text strong style={{ color: '#ff4d4f' }}>
                  {tSystem(masterPasswordOperation === 'remove' ? 'dangerZone.updateMasterPassword.modal.warningSecureRemove' : 'dangerZone.updateMasterPassword.modal.warningSecure')}
                </Text>
              </Space>
            }
            type="warning"
            showIcon
            style={{ marginBottom: 24 }}
          />
          
          {/* Only show password fields for create and update operations */}
          {masterPasswordOperation !== 'remove' && (
            <>
              <Form.Item
                label={tSystem('dangerZone.updateMasterPassword.modal.newPasswordLabel')}
                name="password"
                rules={[
                  { required: true, message: tSystem('dangerZone.updateMasterPassword.modal.newPasswordRequired') },
                  { min: 12, message: tSystem('dangerZone.updateMasterPassword.modal.newPasswordMinLength') },
                  { 
                    pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/,
                    message: tSystem('dangerZone.updateMasterPassword.modal.newPasswordPattern')
                  }
                ]}
              >
                <Input.Password 
                  placeholder={tSystem('dangerZone.updateMasterPassword.modal.newPasswordPlaceholder')}
                  size="large"
                  autoComplete="new-password"
                />
              </Form.Item>
              
              <Form.Item
                label={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordLabel')}
                name="confirmPassword"
                dependencies={['password']}
                rules={[
                  { required: true, message: tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordRequired') },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('password') === value) {
                        return Promise.resolve()
                      }
                      return Promise.reject(new Error(tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordMatch')))
                    },
                  }),
                ]}
              >
                <Input.Password 
                  placeholder={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordPlaceholder')}
                  size="large"
                  autoComplete="new-password"
                />
              </Form.Item>
            </>
          )}

          <Alert
            message={tCommon('general.important')}
            description={tSystem(`dangerZone.updateMasterPassword.modal.importantNote${masterPasswordOperation === 'create' ? 'Create' : masterPasswordOperation === 'remove' ? 'Remove' : ''}`)}
            type="info"
            showIcon
            style={{ marginBottom: 24 }}
          />

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setMasterPasswordModalOpen(false)
                masterPasswordForm.resetFields()
                setMasterPasswordOperation(defaultOperation)
              }}>
                {tSystem('dangerZone.updateMasterPassword.modal.cancel')}
              </Button>
              <Button 
                type="primary" 
                danger
                htmlType="submit"
                loading={updateVaultsMutation.isPending}
                disabled={updateVaultsMutation.isPending}
              >
                {tSystem(`dangerZone.updateMasterPassword.modal.submit${masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)}`)}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Reset Bridge Authorization Modal */}
      <Modal
        title="Reset Bridge Authorization"
        open={resetAuthModal.open}
        onCancel={() => setResetAuthModal({ open: false, bridgeName: '', isCloudManaged: false })}
        footer={[
          <Button 
            key="cancel" 
            onClick={() => setResetAuthModal({ open: false, bridgeName: '', isCloudManaged: false })}
          >
            Cancel
          </Button>,
          <Button 
            key="reset" 
            type="primary" 
            danger
            loading={resetBridgeAuthMutation.isPending}
            onClick={handleResetBridgeAuth}
          >
            Reset Authorization
          </Button>
        ]}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          <Alert
            message="Warning"
            description={`Are you sure you want to reset authorization for bridge "${resetAuthModal.bridgeName}"? This will generate new credentials.`}
            type="warning"
            showIcon
          />
          
          <Form layout="vertical">
            <Form.Item 
              label="Cloud Management"
              help="Check this box if this bridge should be managed by cloud services. Only Global Bridges can be cloud managed."
            >
              <Checkbox
                checked={resetAuthModal.isCloudManaged}
                onChange={(e) => setResetAuthModal(prev => ({ 
                  ...prev, 
                  isCloudManaged: e.target.checked 
                }))}
              >
                Enable Cloud Management
              </Checkbox>
            </Form.Item>
          </Form>
        </Space>
      </Modal>

      {/* Master Password Update Success Modal */}
      <Modal
        open={successModalOpen}
        closable={false}
        footer={null}
        width={500}
      >
        <Result
          status="success"
          title={tSystem(`dangerZone.updateMasterPassword.success.title${completedOperation.charAt(0).toUpperCase() + completedOperation.slice(1)}`)}
          subTitle={
            <Space direction="vertical" size={24} style={{ width: '100%' }}>
              <div>
                <Typography.Paragraph>
                  {tSystem('dangerZone.updateMasterPassword.success.nextSteps')}
                </Typography.Paragraph>
                <ol style={{ textAlign: 'left', paddingLeft: 20 }}>
                  <li>{tSystem('dangerZone.updateMasterPassword.success.step1')}</li>
                  <li>{tSystem(`dangerZone.updateMasterPassword.success.step2${completedOperation === 'remove' ? 'Remove' : ''}`)}</li>
                  <li>{tSystem(`dangerZone.updateMasterPassword.success.step3${completedOperation === 'remove' ? 'Remove' : ''}`)}</li>
                  <li>{tSystem(`dangerZone.updateMasterPassword.success.step4${completedOperation === 'remove' ? 'Remove' : ''}`)}</li>
                </ol>
              </div>
              
              <div style={{ textAlign: 'center' }}>
                <Typography.Title level={4}>
                  {tSystem('dangerZone.updateMasterPassword.success.redirecting')}
                </Typography.Title>
                <Typography.Title level={1} type="danger">
                  {countdown}
                </Typography.Title>
                <Typography.Text type="secondary">
                  {tSystem('dangerZone.updateMasterPassword.success.seconds')}
                </Typography.Text>
              </div>
              
              <Button 
                type="primary" 
                size="large" 
                block
                onClick={() => {
                  dispatch(logout())
                  navigate('/login')
                }}
              >
                {tSystem('dangerZone.updateMasterPassword.success.loginNow')}
              </Button>
            </Space>
          }
        />
      </Modal>

      {/* Change Password Modal */}
      <Modal
        title="Change Password"
        open={changePasswordModalOpen}
        onCancel={() => {
          setChangePasswordModalOpen(false)
          changePasswordForm.resetFields()
        }}
        footer={null}
        width={500}
      >
        <Form
          form={changePasswordForm}
          layout="vertical"
          onFinish={handleChangePassword}
          autoComplete="off"
        >
          <Alert
            message="Password Requirements"
            description={
              <ul style={{ margin: '8px 0 0 20px', fontSize: 14 }}>
                <li>At least 8 characters long</li>
                <li>Contains at least one uppercase letter</li>
                <li>Contains at least one lowercase letter</li>
                <li>Contains at least one number</li>
                <li>Contains at least one special character (@$!%*?&)</li>
              </ul>
            }
            type="info"
            showIcon
            style={{ marginBottom: 24 }}
          />

          <Form.Item
            label="New Password"
            name="newPassword"
            rules={[
              { required: true, message: 'Please enter your new password' },
              { min: 8, message: 'Password must be at least 8 characters long' },
              {
                pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]/,
                message: 'Password must contain uppercase, lowercase, number and special character',
              },
            ]}
          >
            <Input.Password 
              placeholder="Enter new password"
              size="large"
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item
            label="Confirm New Password"
            name="confirmPassword"
            dependencies={['newPassword']}
            rules={[
              { required: true, message: 'Please confirm your new password' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('newPassword') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('Passwords do not match'))
                },
              }),
            ]}
          >
            <Input.Password 
              placeholder="Confirm new password"
              size="large"
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 24 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button
                onClick={() => {
                  setChangePasswordModalOpen(false)
                  changePasswordForm.resetFields()
                }}
              >
                Cancel
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                loading={updateUserPasswordMutation.isPending}
              >
                Change Password
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Two-Factor Authentication Modal */}
      <TwoFactorSettings
        open={twoFactorModalOpen}
        onCancel={() => setTwoFactorModalOpen(false)}
      />

      {/* Import Company Data Modal */}
      <Modal
        title={tSystem('dangerZone.importData.modal.title')}
        open={importModalOpen}
        onCancel={() => {
          setImportModalOpen(false)
          setImportFile(null)
          importForm.resetFields()
          setImportMode('skip')
        }}
        footer={null}
        width={600}
      >
        <Form
          form={importForm}
          layout="vertical"
          onFinish={handleImportCompanyData}
        >
          <Alert
            message={tSystem('dangerZone.importData.modal.warning')}
            description={tSystem('dangerZone.importData.modal.warningText')}
            type="warning"
            showIcon
            style={{ marginBottom: 24 }}
          />

          <Form.Item
            label={tSystem('dangerZone.importData.modal.selectFile')}
            required
          >
            <Upload
              beforeUpload={(file) => {
                setImportFile(file)
                return false // Prevent automatic upload
              }}
              onRemove={() => setImportFile(null)}
              maxCount={1}
              accept=".json"
            >
              <Button icon={<UploadOutlined />}>
                {importFile ? importFile.name : tSystem('dangerZone.importData.modal.selectFile')}
              </Button>
            </Upload>
          </Form.Item>

          <Form.Item
            label={tSystem('dangerZone.importData.modal.importMode')}
          >
            <Radio.Group
              value={importMode}
              onChange={(e) => setImportMode(e.target.value)}
            >
              <Space direction="vertical">
                <Radio value="skip">
                  <Space direction="vertical" size={0}>
                    <Text strong>{tSystem('dangerZone.importData.modal.modeSkip')}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {tSystem('dangerZone.importData.modal.modeSkipDesc')}
                    </Text>
                  </Space>
                </Radio>
                <Radio value="override">
                  <Space direction="vertical" size={0}>
                    <Text strong>{tSystem('dangerZone.importData.modal.modeOverride')}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {tSystem('dangerZone.importData.modal.modeOverrideDesc')}
                    </Text>
                  </Space>
                </Radio>
              </Space>
            </Radio.Group>
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, marginTop: 32 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button
                onClick={() => {
                  setImportModalOpen(false)
                  setImportFile(null)
                  importForm.resetFields()
                  setImportMode('skip')
                }}
              >
                {tSystem('dangerZone.importData.modal.cancel')}
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                loading={importCompanyDataMutation.isPending}
                disabled={!importFile}
              >
                {tSystem('dangerZone.importData.modal.import')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}

export default SystemPage