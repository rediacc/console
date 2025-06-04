import React, { useState } from 'react'
import { Typography, Space, Card, Button, Row, Col } from 'antd'
import { SettingOutlined, BankOutlined, UserOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import VaultEditorModal from '@/components/common/VaultEditorModal'
import { useUpdateCompanyVault, useCompanyVault } from '@/api/queries/company'

const { Title, Text } = Typography

const SettingsPage: React.FC = () => {
  const { t } = useTranslation('settings')
  const [companyVaultModalOpen, setCompanyVaultModalOpen] = useState(false)
  const [userVaultModalOpen, setUserVaultModalOpen] = useState(false)
  
  const { data: companyVault } = useCompanyVault()
  const updateVaultMutation = useUpdateCompanyVault()

  const handleUpdateCompanyVault = async (vault: string, version: number) => {
    await updateVaultMutation.mutateAsync({
      companyVault: vault,
      vaultVersion: version,
    })
    setCompanyVaultModalOpen(false)
  }

  const handleUpdateUserVault = async (vault: string, version: number) => {
    // TODO: Implement user vault update when API is available
    console.log('User vault update:', { vault, version })
    setUserVaultModalOpen(false)
  }

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
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

              <Button
                type="primary"
                icon={<SettingOutlined />}
                onClick={() => setUserVaultModalOpen(true)}
                size="large"
                style={{ marginTop: 16 }}
              >
                {t('personal.configureVault')}
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>

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
    </Space>
  )
}

export default SettingsPage