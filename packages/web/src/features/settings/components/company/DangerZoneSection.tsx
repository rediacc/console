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
import type { TFunction } from 'i18next';

interface DangerZoneSectionProps {
  tSystem: TFunction<'system'>;
  tCommon: TFunction<'common'>;
  onBlockUserRequests: (block: boolean) => void;
  isBlockingUserRequests: boolean;
  onExportVaults: () => void;
  isExportingVaults: boolean;
  onExportCompanyData: () => void;
  isExportingCompanyData: boolean;
  onOpenImportModal: () => void;
  onOpenMasterPasswordModal: () => void;
}

export const DangerZoneSection: React.FC<DangerZoneSectionProps> = ({
  tSystem,
  tCommon,
  onBlockUserRequests,
  isBlockingUserRequests,
  onExportVaults,
  isExportingVaults,
  onExportCompanyData,
  isExportingCompanyData,
  onOpenImportModal,
  onOpenMasterPasswordModal,
}) => (
  <Flex vertical gap={16}>
    <Typography.Title level={3}>
      <WarningOutlined /> {tSystem('dangerZone.title')}
    </Typography.Title>

    <Card>
      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} lg={16}>
          <Space direction="vertical" size={8}>
            <Typography.Title level={5}>
              {tSystem('dangerZone.blockUserRequests.title')}
            </Typography.Title>
            <Typography.Paragraph>
              {tSystem('dangerZone.blockUserRequests.description')}
            </Typography.Paragraph>
          </Space>
        </Col>
        <Col xs={24} lg={8}>
          <Flex justify="flex-end">
            <Popconfirm
              title={tSystem('dangerZone.blockUserRequests.confirmBlock.title')}
              description={
                <Space direction="vertical" size="small">
                  <Typography.Text>
                    {tSystem('dangerZone.blockUserRequests.confirmBlock.description')}
                  </Typography.Text>
                  <ul>
                    <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect1')}</li>
                    <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect2')}</li>
                    <li>{tSystem('dangerZone.blockUserRequests.confirmBlock.effect3')}</li>
                  </ul>
                  <Typography.Text strong>
                    {tSystem('dangerZone.blockUserRequests.confirmBlock.confirm')}
                  </Typography.Text>
                </Space>
              }
              onConfirm={() => onBlockUserRequests(true)}
              okText={tSystem('dangerZone.blockUserRequests.confirmBlock.okText')}
              cancelText={tCommon('general.cancel')}
              okButtonProps={{ danger: true }}
            >
              <Tooltip title={tSystem('dangerZone.blockUserRequests.blockButton')}>
                <Button
                  danger
                  icon={<LockOutlined />}
                  loading={isBlockingUserRequests}
                  aria-label={tSystem('dangerZone.blockUserRequests.blockButton')}
                />
              </Tooltip>
            </Popconfirm>
            <Popconfirm
              title={tSystem('dangerZone.blockUserRequests.confirmUnblock.title')}
              description={tSystem('dangerZone.blockUserRequests.confirmUnblock.description')}
              onConfirm={() => onBlockUserRequests(false)}
              okText={tSystem('dangerZone.blockUserRequests.confirmUnblock.okText')}
              cancelText={tCommon('general.cancel')}
            >
              <Tooltip title={tSystem('dangerZone.blockUserRequests.unblockButton')}>
                <Button
                  icon={<UnlockOutlined />}
                  loading={isBlockingUserRequests}
                  aria-label={tSystem('dangerZone.blockUserRequests.unblockButton')}
                />
              </Tooltip>
            </Popconfirm>
          </Flex>
        </Col>
      </Row>

      {/* eslint-disable-next-line no-restricted-syntax */}
      <Divider style={{ margin: '24px 0' }} />

      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} lg={16}>
          <Space direction="vertical" size={8}>
            <Typography.Title level={5}>
              {tSystem('dangerZone.exportVaults.title')}
            </Typography.Title>
            <Typography.Paragraph>
              {tSystem('dangerZone.exportVaults.description')}
            </Typography.Paragraph>
          </Space>
        </Col>
        <Col xs={24} lg={8}>
          <Flex justify="flex-end">
            <Tooltip title={tSystem('dangerZone.exportVaults.button')}>
              <Button
                icon={<DownloadOutlined />}
                onClick={onExportVaults}
                loading={isExportingVaults}
                data-testid="system-export-vaults-button"
                aria-label={tSystem('dangerZone.exportVaults.button')}
              />
            </Tooltip>
          </Flex>
        </Col>
      </Row>

      {/* eslint-disable-next-line no-restricted-syntax */}
      <Divider style={{ margin: '24px 0' }} />

      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} lg={16}>
          <Space direction="vertical" size={8}>
            <Typography.Title level={5}>{tSystem('dangerZone.exportData.title')}</Typography.Title>
            <Typography.Paragraph>
              {tSystem('dangerZone.exportData.description')}
            </Typography.Paragraph>
          </Space>
        </Col>
        <Col xs={24} lg={8}>
          <Flex justify="flex-end">
            <Tooltip title={tSystem('dangerZone.exportData.button')}>
              <Button
                icon={<ExportOutlined />}
                onClick={onExportCompanyData}
                loading={isExportingCompanyData}
                data-testid="system-export-data-button"
                aria-label={tSystem('dangerZone.exportData.button')}
              />
            </Tooltip>
          </Flex>
        </Col>
      </Row>

      {/* eslint-disable-next-line no-restricted-syntax */}
      <Divider style={{ margin: '24px 0' }} />

      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} lg={16}>
          <Space direction="vertical" size={8}>
            <Typography.Title level={5}>{tSystem('dangerZone.importData.title')}</Typography.Title>
            <Typography.Paragraph>
              {tSystem('dangerZone.importData.description')}
            </Typography.Paragraph>
          </Space>
        </Col>
        <Col xs={24} lg={8}>
          <Flex justify="flex-end">
            <Tooltip title={tSystem('dangerZone.importData.button')}>
              <Button
                danger
                icon={<ImportOutlined />}
                onClick={onOpenImportModal}
                data-testid="system-import-data-button"
                aria-label={tSystem('dangerZone.importData.button')}
              />
            </Tooltip>
          </Flex>
        </Col>
      </Row>

      {/* eslint-disable-next-line no-restricted-syntax */}
      <Divider style={{ margin: '24px 0' }} />

      <Row gutter={[16, 16]} align="middle">
        <Col xs={24} lg={16}>
          <Space direction="vertical" size={8}>
            <Typography.Title level={5}>
              {tSystem('dangerZone.updateMasterPassword.title')}
            </Typography.Title>
            <Typography.Paragraph>
              {tSystem('dangerZone.updateMasterPassword.description')}
            </Typography.Paragraph>
            <ul className="requirements-list">
              <li>{tSystem('dangerZone.updateMasterPassword.effect1')}</li>
              <li>{tSystem('dangerZone.updateMasterPassword.effect2')}</li>
              <li>{tSystem('dangerZone.updateMasterPassword.effect3')}</li>
            </ul>
            <Typography.Text type="danger" strong>
              {tSystem('dangerZone.updateMasterPassword.warning')}
            </Typography.Text>
          </Space>
        </Col>
        <Col xs={24} lg={8}>
          <Flex justify="flex-end">
            <Tooltip title={tSystem('dangerZone.updateMasterPassword.button')}>
              <Button
                danger
                icon={<KeyOutlined />}
                onClick={onOpenMasterPasswordModal}
                data-testid="system-update-master-password-button"
                aria-label={tSystem('dangerZone.updateMasterPassword.button')}
              />
            </Tooltip>
          </Flex>
        </Col>
      </Row>
    </Card>
  </Flex>
);
