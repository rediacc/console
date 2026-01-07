import React from 'react';
import { Alert, Button, Card, Flex, Form, Modal, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  useUpdateUserPassword,
  useUpdateUserVault,
  useGetUserVault,
} from '@/api/api-hooks.generated';
import VaultEditorModal from '@/components/common/VaultEditorModal';
import { PasswordConfirmField, PasswordField } from '@/components/forms/FormFields';
import { featureFlags } from '@/config/featureFlags';
import TwoFactorSettings from '@/features/settings/components/profile/TwoFactorSettings';
import { useDialogState, useModalForm } from '@/hooks';
import { logout } from '@/store/auth/authSlice';
import { RootState } from '@/store/store';
import { ModalSize } from '@/types/modal';
import {
  KeyOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';

const ProfilePage: React.FC = () => {
  const { t } = useTranslation('settings');
  const { t: tSystem } = useTranslation('system');
  const { t: tCommon } = useTranslation('common');
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const currentUser = useSelector((state: RootState) => state.auth.user);

  const {
    form: changePasswordForm,
    isOpen: isChangePasswordOpen,
    open: openChangePassword,
    close: closeChangePassword,
  } = useModalForm<{ newPassword: string; confirmPassword: string }>();
  const twoFactorModal = useDialogState<void>();
  const userVaultModal = useDialogState<void>();

  const { data: userVault, refetch: refetchUserVault } = useGetUserVault();
  const updateUserVaultMutation = useUpdateUserVault();
  const updateUserPasswordMutation = useUpdateUserPassword();

  const handleUpdateUserVault = async (vault: string, version: number) => {
    await updateUserVaultMutation.mutateAsync({
      vaultContent: vault,
      vaultVersion: version,
    });
    userVaultModal.close();
  };

  const handleChangePassword = async (values: { newPassword: string; confirmPassword: string }) => {
    if (!currentUser?.email) return;

    try {
      await updateUserPasswordMutation.mutateAsync({
        userNewPass: values.newPassword,
      });

      closeChangePassword();

      let countdown = 3;
      const modal = Modal.success({
        title: tSystem('personal.changePassword.successTitle'),
        content: tSystem('personal.changePassword.successContent', {
          seconds: countdown,
        }),
        okText: tCommon('actions.logoutNow'),
        onOk: () => {
          dispatch(logout());
          void navigate('/login');
        },
      });

      const timer = setInterval(() => {
        countdown -= 1;
        modal.update({
          content: tSystem('personal.changePassword.successContent', {
            seconds: countdown,
          }),
        });

        if (countdown === 0) {
          clearInterval(timer);
          modal.destroy();
          dispatch(logout());
          void navigate('/login');
        }
      }, 1000);
    } catch {
      // handled by mutation
    }
  };

  return (
    <Flex vertical>
      <Flex vertical>
        <Card>
          <Flex vertical>
            <Flex align="center">
              <UserOutlined />
              <Typography.Title level={4}>{t('personal.title')}</Typography.Title>
            </Flex>

            <Typography.Text>{t('personal.description')}</Typography.Text>

            <Flex wrap align="center">
              {featureFlags.isEnabled('personalVaultConfiguration') && (
                <Tooltip title={t('personal.configureVault')}>
                  <Button
                    icon={<SettingOutlined />}
                    onClick={() => {
                      void refetchUserVault();
                      userVaultModal.open();
                    }}
                    data-testid="system-user-vault-button"
                    aria-label={t('personal.configureVault')}
                  />
                </Tooltip>
              )}
              <Tooltip title={tSystem('actions.changePassword')}>
                <Button
                  icon={<KeyOutlined />}
                  onClick={openChangePassword}
                  data-testid="system-change-password-button"
                  aria-label={tSystem('actions.changePassword')}
                />
              </Tooltip>
              <Tooltip title={tSystem('actions.twoFactorAuth')}>
                <Button
                  icon={<SafetyCertificateOutlined />}
                  onClick={() => twoFactorModal.open()}
                  data-testid="system-two-factor-button"
                  aria-label={tSystem('actions.twoFactorAuth')}
                />
              </Tooltip>
            </Flex>
          </Flex>
        </Card>
      </Flex>

      <VaultEditorModal
        open={userVaultModal.isOpen}
        onCancel={userVaultModal.close}
        onSave={handleUpdateUserVault}
        entityType="USER"
        title={t('personal.modalTitle')}
        initialVault={userVault?.[0]?.vaultContent ?? '{}'}
        initialVersion={userVault?.[0]?.vaultVersion ?? 1}
        loading={updateUserVaultMutation.isPending}
      />

      <Modal
        title={t('personal.changePassword.title')}
        open={isChangePasswordOpen}
        onCancel={closeChangePassword}
        footer={null}
        className={ModalSize.Medium}
        centered
        data-testid="profile-change-password-modal"
      >
        <Form
          form={changePasswordForm}
          layout="vertical"
          onFinish={handleChangePassword}
          autoComplete="off"
        >
          <Alert
            message={t('personal.changePassword.requirementsTitle')}
            description={
              <ul className="requirements-list">
                <li>{t('personal.changePassword.requirement1')}</li>
                <li>{t('personal.changePassword.requirement2')}</li>
                <li>{t('personal.changePassword.requirement3')}</li>
                <li>{t('personal.changePassword.requirement4')}</li>
              </ul>
            }
            type="info"
          />

          <PasswordField
            name="newPassword"
            label={t('personal.changePassword.newPasswordLabel')}
            placeholder={t('personal.changePassword.newPasswordPlaceholder')}
            minLength={8}
            requiredMessage={t('personal.changePassword.newPasswordRequired')}
            minLengthMessage={t('personal.changePassword.newPasswordMin')}
            patternMessage={t('personal.changePassword.newPasswordPattern')}
          />

          <PasswordConfirmField
            name="confirmPassword"
            label={t('personal.changePassword.confirmPasswordLabel')}
            passwordFieldName="newPassword"
            placeholder={t('personal.changePassword.confirmPasswordPlaceholder')}
            requiredMessage={t('personal.changePassword.confirmPasswordRequired')}
            mismatchMessage={t('personal.changePassword.confirmPasswordMismatch')}
          />

          <Form.Item>
            <Flex className="w-full" justify="flex-end">
              <Button
                onClick={closeChangePassword}
                data-testid="profile-change-password-cancel-button"
              >
                {tCommon('actions.cancel')}
              </Button>
              <Button
                htmlType="submit"
                loading={updateUserPasswordMutation.isPending}
                data-testid="profile-change-password-submit-button"
              >
                {t('personal.changePassword.submit')}
              </Button>
            </Flex>
          </Form.Item>
        </Form>
      </Modal>

      <TwoFactorSettings open={twoFactorModal.isOpen} onCancel={twoFactorModal.close} />
    </Flex>
  );
};

export default ProfilePage;
