import React, { useState, useEffect, useRef } from 'react'
import {
  Button,
  Tooltip,
  Row,
  Col,
  Space,
  Popconfirm,
  Modal,
  Upload,
  Radio,
  Result,
  Typography,
  Form,
} from 'antd'
import {
  BankOutlined,
  SettingOutlined,
  LockOutlined,
  UnlockOutlined,
  DownloadOutlined,
  ExportOutlined,
  ImportOutlined,
  WarningOutlined,
  KeyOutlined,
  UploadOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import VaultEditorModal from '@/components/common/VaultEditorModal'
import { ModalSize } from '@/types/modal'
import { RootState } from '@/store/store'
import { logout } from '@/store/auth/authSlice'
import { featureFlags } from '@/config/featureFlags'
import { masterPasswordService } from '@/services/masterPasswordService'
import { encryptString, decryptString } from '@/utils/encryption'
import { showMessage } from '@/utils/messages'
import { useDialogState } from '@/hooks/useDialogState'
import { PasswordField, PasswordConfirmField } from '@/components/forms/FormFields'
import {
  useCompanyVault,
  useUpdateCompanyVault,
  useUpdateCompanyBlockUserRequests,
  useCompanyVaults,
  useUpdateCompanyVaults,
  useExportCompanyData,
  useImportCompanyData,
} from '@/api/queries/company'
import {
  PageWrapper as CompanyPageWrapper,
  SectionStack as CompanySectionStack,
  SectionHeading as CompanySectionHeading,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardActions,
  IconWrapper,
  ModalStack,
  ModalStackLarge,
  ModalActions,
  DangerSection,
  DangerHeading,
  DangerStack,
  RightAlign,
  DangerDivider,
  BulletedList,
  WarningNote,
  DangerText,
  OrderedList,
  RequirementsList,
  CaptionText,
  CenteredBlock,
} from '@/components/ui'
import {
  SettingsCard,
  DangerCard,
  ModalAlert,
  FormItemSpaced,
  FormItemNoMargin,
  FormItemActionsLg,
} from '@/pages/system/styles'

const CompanyPage: React.FC = () => {
  const { t } = useTranslation('settings')
  const { t: tSystem } = useTranslation('system')
  const { t: tCommon } = useTranslation('common')
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const uiMode = useSelector((state: RootState) => state.ui.uiMode)

  const companyVaultModal = useDialogState<void>()
  const masterPasswordModal = useDialogState<void>()
  const [masterPasswordForm] = Form.useForm()
  const [importForm] = Form.useForm()
  const [masterPasswordOperation, setMasterPasswordOperation] = useState<'create' | 'update' | 'remove'>('create')
  const [completedOperation, setCompletedOperation] = useState<'create' | 'update' | 'remove'>('update')
  const successModal = useDialogState<void>()
  const [countdown, setCountdown] = useState(60)
  const countdownInterval = useRef<NodeJS.Timeout | null>(null)
  const importModal = useDialogState<void>()
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importMode, setImportMode] = useState<'skip' | 'override'>('skip')
  const [currentMasterPassword, setCurrentMasterPassword] = useState<string | null>(null)

  const { data: companyVault } = useCompanyVault()
  const updateCompanyVaultMutation = useUpdateCompanyVault()
  const blockUserRequestsMutation = useUpdateCompanyBlockUserRequests()
  const exportVaultsQuery = useCompanyVaults()
  const updateVaultsMutation = useUpdateCompanyVaults()
  const exportCompanyDataQuery = useExportCompanyData()
  const importCompanyDataMutation = useImportCompanyData()

  useEffect(() => {
    const loadMasterPassword = async () => {
      const password = await masterPasswordService.getMasterPassword()
      setCurrentMasterPassword(password)
      setMasterPasswordOperation(password ? 'update' : 'create')
    }
    loadMasterPassword()
  }, [])

  useEffect(() => {
    if (masterPasswordModal.isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create')
    }
  }, [masterPasswordModal.isOpen, currentMasterPassword])

  useEffect(() => {
    if (successModal.isOpen && countdown > 0) {
      countdownInterval.current = setInterval(() => {
        setCountdown((prev) => prev - 1)
      }, 1000)
    } else if (countdown === 0) {
      dispatch(logout())
      navigate('/login')
    }

    return () => {
      if (countdownInterval.current) {
        clearInterval(countdownInterval.current)
      }
    }
  }, [successModal.isOpen, countdown, dispatch, navigate])

  const handleUpdateCompanyVault = async (vault: string, version: number) => {
    await updateCompanyVaultMutation.mutateAsync({
      companyVault: vault,
      vaultVersion: version,
    })
    companyVaultModal.close()
  }

  const handleExportVaults = async () => {
    try {
      const result = await exportVaultsQuery.refetch()
      if (result.data) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0]
        const { allVaults, bridgesWithRequestToken, ...vaultsByType } = result.data

        const exportData = {
          exportDate: new Date().toISOString(),
          vaults: vaultsByType,
          bridgesWithRequestToken,
          metadata: {
            totalVaults: allVaults.length,
            vaultTypes: Object.keys(vaultsByType).map((type) => ({
              type,
              count: (vaultsByType as any)[type]?.length || 0,
            })),
          },
        }

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
    } catch {
      showMessage('error', tSystem('dangerZone.exportVaults.error'))
    }
  }

  const handleExportCompanyData = async () => {
    try {
      const result = await exportCompanyDataQuery.refetch()
      if (result.data) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0]
        const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' })
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
    } catch {
      showMessage('error', tSystem('dangerZone.exportData.error'))
    }
  }

  const handleImportCompanyData = async () => {
    if (!importFile) {
      showMessage('error', tSystem('dangerZone.importData.modal.fileRequired'))
      return
    }

    try {
      const fileContent = await importFile.text()
      try {
        JSON.parse(fileContent)
      } catch {
        showMessage('error', tSystem('dangerZone.importData.modal.invalidFile'))
        return
      }

      await importCompanyDataMutation.mutateAsync({
        companyDataJson: fileContent,
        importMode,
      })

      importModal.close()
      setImportFile(null)
      importForm.resetFields()
    } catch {
      // handled by mutation
    }
  }

  const handleUpdateMasterPassword = async (values: { password?: string; confirmPassword?: string }) => {
    if (updateVaultsMutation.isPending) {
      return
    }

    try {
      const vaultsResult = await exportVaultsQuery.refetch()
      if (!vaultsResult.data || !vaultsResult.data.allVaults) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.noVaults'))
        return
      }

      const vaultUpdates: any[] = []
      const newPassword = masterPasswordOperation === 'remove' ? '' : values.password!

      for (const vault of vaultsResult.data.allVaults) {
        if (vault.decryptedVault && vault.credential && vault.vaultName) {
          try {
            let vaultContent = vault.decryptedVault as string

            if (typeof vaultContent === 'string' && currentMasterPassword && masterPasswordOperation !== 'create') {
              try {
                if (vaultContent.match(/^[A-Za-z0-9+/]+=*$/)) {
                  vaultContent = await decryptString(vaultContent, currentMasterPassword)
                }
              } catch {
                // ignore
              }
            }

            let finalContent = vaultContent
            if (typeof vaultContent === 'string' && masterPasswordOperation !== 'remove') {
              finalContent = await encryptString(vaultContent, newPassword)
            }

            vaultUpdates.push({
              credential: vault.credential,
              name: vault.vaultName,
              content: finalContent,
              version: vault.version || 1,
            })
          } catch (error) {
            showMessage('error', `Failed to process vault ${vault.vaultName}`)
          }
        }
      }

      if (!vaultUpdates.length) {
        showMessage('error', tSystem('dangerZone.updateMasterPassword.error.noVaults'))
        return
      }

      await updateVaultsMutation.mutateAsync(vaultUpdates)
      await blockUserRequestsMutation.mutateAsync(false)

      await masterPasswordService.setMasterPassword(masterPasswordOperation === 'remove' ? null : newPassword)
      setCurrentMasterPassword(masterPasswordOperation === 'remove' ? null : newPassword)

      masterPasswordModal.close()
      masterPasswordForm.resetFields()
      setCompletedOperation(masterPasswordOperation)
      setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create')
      setCountdown(60)
      successModal.open()
    } catch {
      // handled by mutation
    }
  }

  if (uiMode === 'simple') {
    return (
      <CompanyPageWrapper>
        <Result
          status="403"
          title={tSystem('accessControl.expertOnlyTitle', { defaultValue: 'Expert Mode Required' })}
          subTitle={tSystem('accessControl.expertOnlyMessage', { defaultValue: 'Switch to expert mode to manage company settings.' })}
        />
      </CompanyPageWrapper>
    )
  }

  return (
    <CompanyPageWrapper>
      <CompanySectionStack>
        <CompanySectionHeading level={3}>{t('company.title')}</CompanySectionHeading>

        <SettingsCard>
          <CardContent>
            <CardHeader>
              <IconWrapper $size="lg">
                <BankOutlined />
              </IconWrapper>
              <CardTitle level={4}>{t('company.title')}</CardTitle>
            </CardHeader>

            <CardDescription>{t('company.description')}</CardDescription>

            {featureFlags.isEnabled('companyVaultConfiguration') && (
              <CardActions>
                <Tooltip title={t('company.configureVault')}>
                  <Button
                    type="primary"
                    icon={<SettingOutlined />}
                    onClick={() => companyVaultModal.open()}
                    size="large"
                    data-testid="system-company-vault-button"
                    aria-label={t('company.configureVault')}
                  />
                </Tooltip>
              </CardActions>
            )}
          </CardContent>
        </SettingsCard>

        {featureFlags.isEnabled('dangerZone') && (
          <DangerSection>
            <DangerHeading level={3}>
              <WarningOutlined /> {tSystem('dangerZone.title')}
            </DangerHeading>

            <DangerCard>
              <DangerStack>
                <Row gutter={[16, 16]} align="middle">
                  <Col xs={24} lg={16}>
                    <Space direction="vertical" size={8}>
                      <CardTitle level={5}>{tSystem('dangerZone.blockUserRequests.title')}</CardTitle>
                      <CardDescription>{tSystem('dangerZone.blockUserRequests.description')}</CardDescription>
                    </Space>
                  </Col>
                  <Col xs={24} lg={8}>
                    <RightAlign>
                      <Popconfirm
                        title={tSystem('dangerZone.blockUserRequests.confirmBlock.title')}
                        description={
                          <ModalStack>
                            <Typography.Text>{tSystem('dangerZone.blockUserRequests.confirmBlock.description')}</Typography.Text>
                            <BulletedList>
                              <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect1')}</li>
                              <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect2')}</li>
                              <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect3')}</li>
                            </BulletedList>
                            <Typography.Text strong>{tSystem('dangerZone.blockUserRequests.confirmBlock.confirm')}</Typography.Text>
                          </ModalStack>
                        }
                        onConfirm={() => blockUserRequestsMutation.mutate(true)}
                        okText={tSystem('dangerZone.blockUserRequests.confirmBlock.okText')}
                        cancelText={tCommon('general.cancel')}
                        okButtonProps={{ danger: true }}
                      >
                        <Tooltip title={tSystem('dangerZone.blockUserRequests.blockButton')}>
                          <Button
                            type="primary"
                            danger
                            icon={<LockOutlined />}
                            loading={blockUserRequestsMutation.isPending}
                            aria-label={tSystem('dangerZone.blockUserRequests.blockButton')}
                          />
                        </Tooltip>
                      </Popconfirm>
                      <Popconfirm
                        title={tSystem('dangerZone.blockUserRequests.confirmUnblock.title')}
                        description={tSystem('dangerZone.blockUserRequests.confirmUnblock.description')}
                        onConfirm={() => blockUserRequestsMutation.mutate(false)}
                        okText={tSystem('dangerZone.blockUserRequests.confirmUnblock.okText')}
                        cancelText={tCommon('general.cancel')}
                      >
                        <Tooltip title={tSystem('dangerZone.blockUserRequests.unblockButton')}>
                          <Button
                            type="primary"
                            icon={<UnlockOutlined />}
                            loading={blockUserRequestsMutation.isPending}
                            aria-label={tSystem('dangerZone.blockUserRequests.unblockButton')}
                          />
                        </Tooltip>
                      </Popconfirm>
                    </RightAlign>
                  </Col>
                </Row>

                <DangerDivider />

                <Row gutter={[16, 16]} align="middle">
                  <Col xs={24} lg={16}>
                    <Space direction="vertical" size={8}>
                      <CardTitle level={5}>{tSystem('dangerZone.exportVaults.title')}</CardTitle>
                      <CardDescription>{tSystem('dangerZone.exportVaults.description')}</CardDescription>
                    </Space>
                  </Col>
                  <Col xs={24} lg={8}>
                    <RightAlign>
                      <Tooltip title={tSystem('dangerZone.exportVaults.button')}>
                        <Button
                          type="primary"
                          icon={<DownloadOutlined />}
                          onClick={handleExportVaults}
                          loading={exportVaultsQuery.isFetching}
                          data-testid="system-export-vaults-button"
                          aria-label={tSystem('dangerZone.exportVaults.button')}
                        />
                      </Tooltip>
                    </RightAlign>
                  </Col>
                </Row>

                <DangerDivider />

                <Row gutter={[16, 16]} align="middle">
                  <Col xs={24} lg={16}>
                    <Space direction="vertical" size={8}>
                      <CardTitle level={5}>{tSystem('dangerZone.exportData.title')}</CardTitle>
                      <CardDescription>{tSystem('dangerZone.exportData.description')}</CardDescription>
                    </Space>
                  </Col>
                  <Col xs={24} lg={8}>
                    <RightAlign>
                      <Tooltip title={tSystem('dangerZone.exportData.button')}>
                        <Button
                          type="primary"
                          icon={<ExportOutlined />}
                          onClick={handleExportCompanyData}
                          loading={exportCompanyDataQuery.isFetching}
                          data-testid="system-export-data-button"
                          aria-label={tSystem('dangerZone.exportData.button')}
                        />
                      </Tooltip>
                    </RightAlign>
                  </Col>
                </Row>

                <DangerDivider />

                <Row gutter={[16, 16]} align="middle">
                  <Col xs={24} lg={16}>
                    <Space direction="vertical" size={8}>
                      <CardTitle level={5}>{tSystem('dangerZone.importData.title')}</CardTitle>
                      <CardDescription>{tSystem('dangerZone.importData.description')}</CardDescription>
                    </Space>
                  </Col>
                  <Col xs={24} lg={8}>
                    <RightAlign>
                      <Tooltip title={tSystem('dangerZone.importData.button')}>
                        <Button
                          type="primary"
                          danger
                          icon={<ImportOutlined />}
                          onClick={() => importModal.open()}
                          data-testid="system-import-data-button"
                          aria-label={tSystem('dangerZone.importData.button')}
                        />
                      </Tooltip>
                    </RightAlign>
                  </Col>
                </Row>

                <DangerDivider />

                <Row gutter={[16, 16]} align="middle">
                  <Col xs={24} lg={16}>
                    <Space direction="vertical" size={8}>
                      <CardTitle level={5}>{tSystem('dangerZone.updateMasterPassword.title')}</CardTitle>
                      <CardDescription>{tSystem('dangerZone.updateMasterPassword.description')}</CardDescription>
                      <RequirementsList>
                        <li>{tSystem('dangerZone.updateMasterPassword.effect1')}</li>
                        <li>{tSystem('dangerZone.updateMasterPassword.effect2')}</li>
                        <li>{tSystem('dangerZone.updateMasterPassword.effect3')}</li>
                      </RequirementsList>
                      <WarningNote type="secondary" strong>
                        {tSystem('dangerZone.updateMasterPassword.warning')}
                      </WarningNote>
                    </Space>
                  </Col>
                  <Col xs={24} lg={8}>
                    <RightAlign>
                      <Tooltip title={tSystem('dangerZone.updateMasterPassword.button')}>
                        <Button
                          type="primary"
                          danger
                          icon={<KeyOutlined />}
                          onClick={() => masterPasswordModal.open()}
                          data-testid="system-update-master-password-button"
                          aria-label={tSystem('dangerZone.updateMasterPassword.button')}
                        />
                      </Tooltip>
                    </RightAlign>
                  </Col>
                </Row>
              </DangerStack>
            </DangerCard>
          </DangerSection>
        )}
      </CompanySectionStack>

      <VaultEditorModal
        open={companyVaultModal.isOpen}
        onCancel={companyVaultModal.close}
        onSave={handleUpdateCompanyVault}
        entityType="COMPANY"
        title={t('company.modalTitle')}
        initialVault={companyVault?.vault || '{}'}
        initialVersion={companyVault?.vaultVersion || 1}
        loading={updateCompanyVaultMutation.isPending}
      />

      <Modal
        title={
          currentMasterPassword
            ? tSystem('dangerZone.updateMasterPassword.modal.title')
            : tSystem('dangerZone.updateMasterPassword.modal.operationCreate')
        }
        open={masterPasswordModal.isOpen}
        onCancel={() => {
          masterPasswordModal.close()
          masterPasswordForm.resetFields()
          setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create')
        }}
        footer={null}
        className={ModalSize.Medium}
      >
        <Form layout="vertical" form={masterPasswordForm} onFinish={handleUpdateMasterPassword}>
          {currentMasterPassword && (
            <FormItemSpaced label={tSystem('dangerZone.updateMasterPassword.modal.operationType')}>
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
            </FormItemSpaced>
          )}

          <ModalAlert
            message={
              <>
                {'\u26A0\uFE0F'}{' '}
                {tSystem('dangerZone.updateMasterPassword.modal.warningTitle').replace('⚠️ ', '')}
              </>
            }
            description={
              <Space direction="vertical" size={8}>
                <Typography.Text>
                  {tSystem(
                    `dangerZone.updateMasterPassword.modal.warningDescription${
                      masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)
                    }`
                  )}
                </Typography.Text>
                <BulletedList>
                  <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect1')}</li>
                  <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect2')}</li>
                  <li>
                    {tSystem(
                      `dangerZone.updateMasterPassword.modal.warningEffect3${
                        masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)
                      }`
                    )}
                  </li>
                  {masterPasswordOperation !== 'remove' && (
                    <li>{tSystem('dangerZone.updateMasterPassword.modal.warningEffect4')}</li>
                  )}
                </BulletedList>
                <Typography.Text strong>
                  {tSystem('dangerZone.updateMasterPassword.modal.warningPermanent')}
                </Typography.Text>
                <DangerText strong>
                  {tSystem(
                    masterPasswordOperation === 'remove'
                      ? 'dangerZone.updateMasterPassword.modal.warningSecureRemove'
                      : 'dangerZone.updateMasterPassword.modal.warningSecure'
                  )}
                </DangerText>
              </Space>
            }
            type="warning"
            showIcon
          />

          {masterPasswordOperation !== 'remove' && (
            <>
              <PasswordField
                name="password"
                label={tSystem('dangerZone.updateMasterPassword.modal.newPasswordLabel')}
                placeholder={tSystem('dangerZone.updateMasterPassword.modal.newPasswordPlaceholder')}
                minLength={12}
                requiredMessage={tSystem('dangerZone.updateMasterPassword.modal.newPasswordRequired')}
                minLengthMessage={tSystem('dangerZone.updateMasterPassword.modal.newPasswordMinLength')}
                patternMessage={tSystem('dangerZone.updateMasterPassword.modal.newPasswordPattern')}
              />

              <PasswordConfirmField
                name="confirmPassword"
                label={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordLabel')}
                passwordFieldName="password"
                placeholder={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordPlaceholder')}
                requiredMessage={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordRequired')}
                mismatchMessage={tSystem('dangerZone.updateMasterPassword.modal.confirmPasswordMatch')}
              />
            </>
          )}

          <ModalAlert
            message={tCommon('general.important')}
            description={tSystem(
              `dangerZone.updateMasterPassword.modal.importantNote${
                masterPasswordOperation === 'create'
                  ? 'Create'
                  : masterPasswordOperation === 'remove'
                    ? 'Remove'
                    : ''
              }`
            )}
            type="info"
            showIcon
          />

          <FormItemNoMargin>
            <ModalActions>
              <Button
                onClick={() => {
                  masterPasswordModal.close()
                  masterPasswordForm.resetFields()
                  setMasterPasswordOperation(currentMasterPassword ? 'update' : 'create')
                }}
                data-testid="system-master-password-cancel-button"
              >
                {tSystem('dangerZone.updateMasterPassword.modal.cancel')}
              </Button>
              <Button
                type="primary"
                danger
                htmlType="submit"
                loading={updateVaultsMutation.isPending}
                disabled={updateVaultsMutation.isPending}
                data-testid="system-master-password-submit-button"
              >
                {tSystem(
                  `dangerZone.updateMasterPassword.modal.submit${
                    masterPasswordOperation.charAt(0).toUpperCase() + masterPasswordOperation.slice(1)
                  }`
                )}
              </Button>
            </ModalActions>
          </FormItemNoMargin>
        </Form>
      </Modal>

      <Modal
        open={successModal.isOpen}
        closable={false}
        footer={null}
        className={ModalSize.Medium}
      >
        <Result
          status="success"
          title={tSystem(
            `dangerZone.updateMasterPassword.success.title${
              completedOperation.charAt(0).toUpperCase() + completedOperation.slice(1)
            }`
          )}
          subTitle={
            <ModalStackLarge>
              <div>
                <Typography.Paragraph>
                  {tSystem('dangerZone.updateMasterPassword.success.nextSteps')}
                </Typography.Paragraph>
                <OrderedList>
                  <li>{tSystem('dangerZone.updateMasterPassword.success.step1')}</li>
                  <li>
                    {tSystem(
                      `dangerZone.updateMasterPassword.success.step2${
                        completedOperation === 'remove' ? 'Remove' : ''
                      }`
                    )}
                  </li>
                  <li>
                    {tSystem(
                      `dangerZone.updateMasterPassword.success.step3${
                        completedOperation === 'remove' ? 'Remove' : ''
                      }`
                    )}
                  </li>
                  <li>
                    {tSystem(
                      `dangerZone.updateMasterPassword.success.step4${
                        completedOperation === 'remove' ? 'Remove' : ''
                      }`
                    )}
                  </li>
                </OrderedList>
              </div>

              <CenteredBlock>
                <Typography.Title level={4}>
                  {tSystem('dangerZone.updateMasterPassword.success.redirecting')}
                </Typography.Title>
                <Typography.Title level={1} type="danger">
                  {countdown}
                </Typography.Title>
                <Typography.Text type="secondary">
                  {tSystem('dangerZone.updateMasterPassword.success.seconds')}
                </Typography.Text>
              </CenteredBlock>

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
            </ModalStackLarge>
          }
        />
      </Modal>

      <Modal
        title={tSystem('dangerZone.importData.modal.title')}
        open={importModal.isOpen}
        onCancel={() => {
          importModal.close()
          setImportFile(null)
          importForm.resetFields()
          setImportMode('skip')
        }}
        footer={null}
        className={ModalSize.Medium}
      >
        <Form form={importForm} layout="vertical" onFinish={handleImportCompanyData}>
          <ModalAlert
            message={tSystem('dangerZone.importData.modal.warning')}
            description={tSystem('dangerZone.importData.modal.warningText')}
            type="warning"
            showIcon
          />

          <Form.Item label={tSystem('dangerZone.importData.modal.selectFile')} required>
            <Upload
              beforeUpload={(file) => {
                setImportFile(file)
                return false
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

          <Form.Item label={tSystem('dangerZone.importData.modal.importMode')}>
            <Radio.Group value={importMode} onChange={(e) => setImportMode(e.target.value)}>
              <Space direction="vertical">
                <Radio value="skip">
                  <Space direction="vertical" size={0}>
                    <Typography.Text strong>
                      {tSystem('dangerZone.importData.modal.modeSkip')}
                    </Typography.Text>
                    <CaptionText>{tSystem('dangerZone.importData.modal.modeSkipDesc')}</CaptionText>
                  </Space>
                </Radio>
                <Radio value="override">
                  <Space direction="vertical" size={0}>
                    <Typography.Text strong>
                      {tSystem('dangerZone.importData.modal.modeOverride')}
                    </Typography.Text>
                    <CaptionText>{tSystem('dangerZone.importData.modal.modeOverrideDesc')}</CaptionText>
                  </Space>
                </Radio>
              </Space>
            </Radio.Group>
          </Form.Item>

          <FormItemActionsLg>
            <ModalActions>
              <Button
                onClick={() => {
                  importModal.close()
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
            </ModalActions>
          </FormItemActionsLg>
        </Form>
      </Modal>
    </CompanyPageWrapper>
  )
}

export default CompanyPage
