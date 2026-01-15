import React from 'react';
import {
  Button,
  Card,
  Col,
  Divider,
  Flex,
  Popconfirm,
  Row,
  Space,
  Tooltip,
  Typography,
} from 'antd';
import {
  DownloadOutlined,
  ExportOutlined,
  ImportOutlined,
  KeyOutlined,
  LockOutlined,
  UnlockOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';

interface DangerZoneSectionProps {
  t: TypedTFunction;
  onBlockUserRequests: (block: boolean) => void;
  isBlockingUserRequests: boolean;
  onExportVaults: () => void;
  isExportingVaults: boolean;
  onExportOrganizationData: () => void;
  isExportingOrganizationData: boolean;
  onOpenImportModal: () => void;
  onOpenMasterPasswordModal: () => void;
}

export const DangerZoneSection: React.FC<DangerZoneSectionProps> = ({
  t,
  onBlockUserRequests,
  isBlockingUserRequests,
  onExportVaults,
  isExportingVaults,
  onExportOrganizationData,
  isExportingOrganizationData,
  onOpenImportModal,
  onOpenMasterPasswordModal,
}) => {
  return (
    <Flex vertical>
      <Typography.Title level={3}>
        <WarningOutlined /> {t('system:dangerZone.title')}
      </Typography.Title>

      <Card>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} lg={16}>
            <Space direction="vertical" size={8}>
              <Typography.Title level={5}>
                {t('system:dangerZone.blockUserRequests.title')}
              </Typography.Title>
              <Typography.Paragraph>
                {t('system:dangerZone.blockUserRequests.description')}
              </Typography.Paragraph>
            </Space>
          </Col>
          <Col xs={24} lg={8}>
            <Flex justify="flex-end">
              <Popconfirm
                title={t('system:dangerZone.blockUserRequests.confirmBlock.title')}
                description={
                  <Space direction="vertical" size="small">
                    <Typography.Text>
                      {t('system:dangerZone.blockUserRequests.confirmBlock.description')}
                    </Typography.Text>
                    <ul>
                      <li>{t('system:dangerZone.blockUserRequests.confirmBlock.effect1')}</li>
                      <li>{t('system:dangerZone.blockUserRequests.confirmBlock.effect2')}</li>
                      <li>{t('system:dangerZone.blockUserRequests.confirmBlock.effect3')}</li>
                    </ul>
                    <Typography.Text strong>
                      {t('system:dangerZone.blockUserRequests.confirmBlock.confirm')}
                    </Typography.Text>
                  </Space>
                }
                onConfirm={() => onBlockUserRequests(true)}
                okText={t('system:dangerZone.blockUserRequests.confirmBlock.okText')}
                cancelText={t('common:general.cancel')}
                okButtonProps={{ danger: true }}
              >
                <Tooltip title={t('system:dangerZone.blockUserRequests.blockButton')}>
                  <Button
                    danger
                    icon={<LockOutlined />}
                    loading={isBlockingUserRequests}
                    data-testid="system-block-user-requests-button"
                    aria-label={t('system:dangerZone.blockUserRequests.blockButton')}
                  />
                </Tooltip>
              </Popconfirm>
              <Popconfirm
                title={t('system:dangerZone.blockUserRequests.confirmUnblock.title')}
                description={t('system:dangerZone.blockUserRequests.confirmUnblock.description')}
                onConfirm={() => onBlockUserRequests(false)}
                okText={t('system:dangerZone.blockUserRequests.confirmUnblock.okText')}
                cancelText={t('common:general.cancel')}
              >
                <Tooltip title={t('system:dangerZone.blockUserRequests.unblockButton')}>
                  <Button
                    icon={<UnlockOutlined />}
                    loading={isBlockingUserRequests}
                    data-testid="system-unblock-user-requests-button"
                    aria-label={t('system:dangerZone.blockUserRequests.unblockButton')}
                  />
                </Tooltip>
              </Popconfirm>
            </Flex>
          </Col>
        </Row>

        <Divider className="my-6" />

        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} lg={16}>
            <Space direction="vertical" size={8}>
              <Typography.Title level={5}>
                {t('system:dangerZone.exportVaults.title')}
              </Typography.Title>
              <Typography.Paragraph>
                {t('system:dangerZone.exportVaults.description')}
              </Typography.Paragraph>
            </Space>
          </Col>
          <Col xs={24} lg={8}>
            <Flex justify="flex-end">
              <Tooltip title={t('system:dangerZone.exportVaults.button')}>
                <Button
                  icon={<DownloadOutlined />}
                  onClick={onExportVaults}
                  loading={isExportingVaults}
                  data-testid="system-export-vaults-button"
                  aria-label={t('system:dangerZone.exportVaults.button')}
                />
              </Tooltip>
            </Flex>
          </Col>
        </Row>

        <Divider className="my-6" />

        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} lg={16}>
            <Space direction="vertical" size={8}>
              <Typography.Title level={5}>
                {t('system:dangerZone.exportData.title')}
              </Typography.Title>
              <Typography.Paragraph>
                {t('system:dangerZone.exportData.description')}
              </Typography.Paragraph>
            </Space>
          </Col>
          <Col xs={24} lg={8}>
            <Flex justify="flex-end">
              <Tooltip title={t('system:dangerZone.exportData.button')}>
                <Button
                  icon={<ExportOutlined />}
                  onClick={onExportOrganizationData}
                  loading={isExportingOrganizationData}
                  data-testid="system-export-data-button"
                  aria-label={t('system:dangerZone.exportData.button')}
                />
              </Tooltip>
            </Flex>
          </Col>
        </Row>

        <Divider className="my-6" />

        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} lg={16}>
            <Space direction="vertical" size={8}>
              <Typography.Title level={5}>
                {t('system:dangerZone.importData.title')}
              </Typography.Title>
              <Typography.Paragraph>
                {t('system:dangerZone.importData.description')}
              </Typography.Paragraph>
            </Space>
          </Col>
          <Col xs={24} lg={8}>
            <Flex justify="flex-end">
              <Tooltip title={t('system:dangerZone.importData.button')}>
                <Button
                  danger
                  icon={<ImportOutlined />}
                  onClick={onOpenImportModal}
                  data-testid="system-import-data-button"
                  aria-label={t('system:dangerZone.importData.button')}
                />
              </Tooltip>
            </Flex>
          </Col>
        </Row>

        <Divider className="my-6" />

        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} lg={16}>
            <Space direction="vertical" size={8}>
              <Typography.Title level={5}>
                {t('system:dangerZone.updateMasterPassword.title')}
              </Typography.Title>
              <Typography.Paragraph>
                {t('system:dangerZone.updateMasterPassword.description')}
              </Typography.Paragraph>
              <ul className="requirements-list">
                <li>{t('system:dangerZone.updateMasterPassword.effect1')}</li>
                <li>{t('system:dangerZone.updateMasterPassword.effect2')}</li>
                <li>{t('system:dangerZone.updateMasterPassword.effect3')}</li>
              </ul>
              <Typography.Text type="danger" strong>
                {t('system:dangerZone.updateMasterPassword.warning')}
              </Typography.Text>
            </Space>
          </Col>
          <Col xs={24} lg={8}>
            <Flex justify="flex-end">
              <Tooltip title={t('system:dangerZone.updateMasterPassword.button')}>
                <Button
                  danger
                  icon={<KeyOutlined />}
                  onClick={onOpenMasterPasswordModal}
                  data-testid="system-update-master-password-button"
                  aria-label={t('system:dangerZone.updateMasterPassword.button')}
                />
              </Tooltip>
            </Flex>
          </Col>
        </Row>
      </Card>
    </Flex>
  );
};
