import React from 'react'
import { Button, Tooltip, Modal, Form } from 'antd'
import { useTranslation } from 'react-i18next'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import {
  UserOutlined,
  SettingOutlined,
  KeyOutlined,
  SafetyCertificateOutlined,
} from '@/utils/optimizedIcons'
import { RootState } from '@/store/store'
import { logout } from '@/store/auth/authSlice'
import { featureFlags } from '@/config/featureFlags'
import { useUserVault, useUpdateUserVault, useUpdateUserPassword } from '@/api/queries/users'
import VaultEditorModal from '@/components/common/VaultEditorModal'
import TwoFactorSettings from '@/components/settings/TwoFactorSettings'
import { ModalSize } from '@/types/modal'
import { useDialogState, useModalForm } from '@/hooks'
import { PasswordField, PasswordConfirmField } from '@/components/forms/FormFields'
import {
  ProfilePageWrapper,
  ProfileSectionStack,
  ProfileSectionHeading,
} from './styles'
import {
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardActions,
  IconWrapper,
  RequirementsList,
  ModalActions,
} from '@/components/ui'
import {
  SettingsCard,
  ModalAlert,
  FormItemActions,
} from '@/pages/system/styles'

const ProfilePage: React.FC = () => {
  const { t } = useTranslation('settings')
  const { t: tSystem } = useTranslation('system')
  const { t: tCommon } = useTranslation('common')
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const currentUser = useSelector((state: RootState) => state.auth.user)

  const { form: changePasswordForm, isOpen: isChangePasswordOpen, open: openChangePassword, close: closeChangePassword } = useModalForm<{ newPassword: string; confirmPassword: string }>()
  const twoFactorModal = useDialogState<void>()
  const userVaultModal = useDialogState<void>()

  const { data: userVault, refetch: refetchUserVault } = useUserVault()
  const updateUserVaultMutation = useUpdateUserVault()
  const updateUserPasswordMutation = useUpdateUserPassword()

  const handleUpdateUserVault = async (vault: string, version: number) => {
    await updateUserVaultMutation.mutateAsync({
      userVault: vault,
      vaultVersion: version,
    })
    userVaultModal.close()
  }

  const handleChangePassword = async (values: { newPassword: string; confirmPassword: string }) => {
    if (!currentUser?.email) return

    try {
      await updateUserPasswordMutation.mutateAsync({
        userEmail: currentUser.email,
        newPassword: values.newPassword,
      })

      closeChangePassword()

      let countdown = 3
      const modal = Modal.success({
        title: tSystem('personal.changePassword.successTitle', { defaultValue: 'Password Changed Successfully' }),
        content: tSystem('personal.changePassword.successContent', {
          defaultValue: `Your password has been changed. You will be logged out in ${countdown} seconds...`,
          seconds: countdown,
        }),
        okText: tCommon('actions.logoutNow', { defaultValue: 'Logout Now' }),
        onOk: () => {
          dispatch(logout())
          navigate('/login')
        },
      })

      const timer = setInterval(() => {
        countdown -= 1
        modal.update({
          content: tSystem('personal.changePassword.successContent', {
            defaultValue: `Your password has been changed. You will be logged out in ${countdown} seconds...`,
            seconds: countdown,
          }),
        })

        if (countdown === 0) {
          clearInterval(timer)
          modal.destroy()
          dispatch(logout())
          navigate('/login')
        }
      }, 1000)
    } catch {
      // handled by mutation
    }
  }

  return (
    <ProfilePageWrapper>
      <ProfileSectionStack>
        <ProfileSectionHeading level={3}>{t('personal.title')}</ProfileSectionHeading>

        <SettingsCard>
          <CardContent>
            <CardHeader>
              <IconWrapper $size="lg">
                <UserOutlined />
              </IconWrapper>
              <CardTitle level={4}>{t('personal.title')}</CardTitle>
            </CardHeader>

            <CardDescription>{t('personal.description')}</CardDescription>

            <CardActions>
              {featureFlags.isEnabled('personalVaultConfiguration') && (
                <Tooltip title={t('personal.configureVault')}>
                  <Button
                    type="primary"
                    icon={<SettingOutlined />}
                    onClick={() => {
                      refetchUserVault()
                      userVaultModal.open()
                    }}
                    size="large"
                    data-testid="system-user-vault-button"
                    aria-label={t('personal.configureVault')}
                  />
                </Tooltip>
              )}
              <Tooltip title={tSystem('actions.changePassword')}>
                <Button
                  type="primary"
                  icon={<KeyOutlined />}
                  onClick={openChangePassword}
                  size="large"
                  data-testid="system-change-password-button"
                  aria-label={tSystem('actions.changePassword')}
                />
              </Tooltip>
              <Tooltip title={tSystem('actions.twoFactorAuth')}>
                <Button
                  type="primary"
                  icon={<SafetyCertificateOutlined />}
                  onClick={() => twoFactorModal.open()}
                  size="large"
                  data-testid="system-two-factor-button"
                  aria-label={tSystem('actions.twoFactorAuth')}
                />
              </Tooltip>
            </CardActions>
          </CardContent>
        </SettingsCard>
      </ProfileSectionStack>

      <VaultEditorModal
        open={userVaultModal.isOpen}
        onCancel={userVaultModal.close}
        onSave={handleUpdateUserVault}
        entityType="USER"
        title={t('personal.modalTitle')}
        initialVault={userVault?.vault || '{}'}
        initialVersion={userVault?.vaultVersion || 1}
        loading={updateUserVaultMutation.isPending}
      />

      <Modal
        title={t('personal.changePassword.title', { defaultValue: 'Change Password' })}
        open={isChangePasswordOpen}
        onCancel={closeChangePassword}
        footer={null}
        className={ModalSize.Medium}
      >
        <Form form={changePasswordForm} layout="vertical" onFinish={handleChangePassword} autoComplete="off">
          <ModalAlert
            message={t('personal.changePassword.requirementsTitle', { defaultValue: 'Password Requirements' })}
            description={
              <RequirementsList>
                <li>{t('personal.changePassword.requirement1', { defaultValue: 'At least 8 characters long' })}</li>
                <li>{t('personal.changePassword.requirement2', { defaultValue: 'Contains uppercase and lowercase letters' })}</li>
                <li>{t('personal.changePassword.requirement3', { defaultValue: 'Contains at least one number' })}</li>
                <li>{t('personal.changePassword.requirement4', { defaultValue: 'Contains at least one special character' })}</li>
              </RequirementsList>
            }
            type="info"
            showIcon
          />

          <PasswordField
            name="newPassword"
            label={t('personal.changePassword.newPasswordLabel', { defaultValue: 'New Password' })}
            placeholder={t('personal.changePassword.newPasswordPlaceholder', { defaultValue: 'Enter new password' })}
            minLength={8}
            requiredMessage={t('personal.changePassword.newPasswordRequired', { defaultValue: 'Please enter your new password' })}
            minLengthMessage={t('personal.changePassword.newPasswordMin', { defaultValue: 'Password must be at least 8 characters long' })}
            patternMessage={t('personal.changePassword.newPasswordPattern', { defaultValue: 'Password must contain uppercase, lowercase, number and special character' })}
          />

          <PasswordConfirmField
            name="confirmPassword"
            label={t('personal.changePassword.confirmPasswordLabel', { defaultValue: 'Confirm New Password' })}
            passwordFieldName="newPassword"
            placeholder={t('personal.changePassword.confirmPasswordPlaceholder', { defaultValue: 'Confirm new password' })}
            requiredMessage={t('personal.changePassword.confirmPasswordRequired', { defaultValue: 'Please confirm your new password' })}
            mismatchMessage={t('personal.changePassword.confirmPasswordMismatch', { defaultValue: 'Passwords do not match' })}
          />

          <FormItemActions>
            <ModalActions>
              <Button onClick={closeChangePassword}>
                {tCommon('actions.cancel')}
              </Button>
              <Button type="primary" htmlType="submit" loading={updateUserPasswordMutation.isPending}>
                {t('personal.changePassword.submit', { defaultValue: 'Change Password' })}
              </Button>
            </ModalActions>
          </FormItemActions>
        </Form>
      </Modal>

      <TwoFactorSettings open={twoFactorModal.isOpen} onCancel={twoFactorModal.close} />
    </ProfilePageWrapper>
  )
}

export default ProfilePage
