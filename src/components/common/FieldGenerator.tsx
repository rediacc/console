import React, { useState } from 'react'
import { Button, Popover, Space, Radio, message, Spin, Tooltip } from 'antd'
import { KeyOutlined, ReloadOutlined, CopyOutlined, CheckOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { 
  generateSSHKeyPair, 
  generateRepositoryCredential,
  GenerationOptions 
} from '@/utils/cryptoGenerators'

interface FieldGeneratorProps {
  fieldName: string
  fieldType: 'ssh_keys' | 'repository_credential'
  onGenerate: (values: Record<string, string>) => void
  entityType?: string
}

const FieldGenerator: React.FC<FieldGeneratorProps> = ({
  fieldName,
  fieldType,
  onGenerate,
  entityType
}) => {
  const { t } = useTranslation('common')
  const [visible, setVisible] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generatedValues, setGeneratedValues] = useState<Record<string, string>>({})
  const [keyOptions, setKeyOptions] = useState<GenerationOptions>({
    keyType: 'rsa',
    keySize: 2048,
    comment: `${entityType || 'generated'}-${new Date().toISOString().split('T')[0]}`
  })
  const [copiedField, setCopiedField] = useState<string | null>(null)

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      if (fieldType === 'ssh_keys') {
        const keys = await generateSSHKeyPair(keyOptions)
        setGeneratedValues({
          SSH_PRIVATE_KEY: keys.privateKey,
          SSH_PUBLIC_KEY: keys.publicKey
        })
      } else if (fieldType === 'repository_credential') {
        const credential = generateRepositoryCredential()
        setGeneratedValues({
          credential: credential
        })
      }
      message.success(t('fieldGenerator.generationSuccess'))
    } catch (error) {
      console.error('Generation error:', error)
      message.error(t('fieldGenerator.generationError'))
    } finally {
      setGenerating(false)
    }
  }

  const handleApply = () => {
    onGenerate(generatedValues)
    setVisible(false)
    setGeneratedValues({})
    message.success(t('fieldGenerator.applied'))
  }

  const handleCopy = (field: string, value: string) => {
    navigator.clipboard.writeText(value).then(() => {
      setCopiedField(field)
      message.success(t('fieldGenerator.copied'))
      setTimeout(() => setCopiedField(null), 2000)
    }).catch(() => {
      message.error(t('fieldGenerator.copyError'))
    })
  }

  const renderSSHKeyOptions = () => (
    <Space direction="vertical" style={{ width: '100%' }}>
      <div>
        <label style={{ fontWeight: 500 }}>{t('fieldGenerator.keyType')}</label>
        <Radio.Group 
          value={keyOptions.keyType} 
          onChange={(e) => setKeyOptions({ ...keyOptions, keyType: e.target.value })}
          style={{ display: 'block', marginTop: 8 }}
        >
          <Radio value="rsa">RSA</Radio>
          <Radio value="ed25519" disabled>
            Ed25519 <span style={{ color: '#999' }}>({t('fieldGenerator.comingSoon')})</span>
          </Radio>
        </Radio.Group>
      </div>
      
      {keyOptions.keyType === 'rsa' && (
        <div>
          <label style={{ fontWeight: 500 }}>{t('fieldGenerator.keySize')}</label>
          <Radio.Group 
            value={keyOptions.keySize} 
            onChange={(e) => setKeyOptions({ ...keyOptions, keySize: e.target.value })}
            style={{ display: 'block', marginTop: 8 }}
          >
            <Radio value={2048}>2048 bits</Radio>
            <Radio value={4096}>4096 bits ({t('fieldGenerator.moreSecure')})</Radio>
          </Radio.Group>
        </div>
      )}
    </Space>
  )

  const renderGeneratedValues = () => (
    <Space direction="vertical" style={{ width: '100%' }}>
      {Object.entries(generatedValues).map(([field, value]) => (
        <div key={field} style={{ 
          padding: 12, 
          background: '#f5f5f5', 
          borderRadius: 6,
          fontFamily: 'monospace',
          fontSize: 12
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong>{field}:</strong>
            <Button
              size="small"
              icon={copiedField === field ? <CheckOutlined /> : <CopyOutlined />}
              onClick={() => handleCopy(field, value)}
            >
              {copiedField === field ? t('fieldGenerator.copied') : t('fieldGenerator.copy')}
            </Button>
          </div>
          <div style={{ 
            wordBreak: 'break-all', 
            maxHeight: 100, 
            overflow: 'auto',
            padding: 8,
            background: '#fff',
            border: '1px solid #d9d9d9',
            borderRadius: 4
          }}>
            {value}
          </div>
        </div>
      ))}
    </Space>
  )

  const popoverContent = (
    <div style={{ width: 400 }}>
      {fieldType === 'ssh_keys' && !Object.keys(generatedValues).length && renderSSHKeyOptions()}
      
      {Object.keys(generatedValues).length > 0 && renderGeneratedValues()}
      
      <Space style={{ marginTop: 16, width: '100%', justifyContent: 'flex-end' }}>
        {Object.keys(generatedValues).length === 0 ? (
          <Button 
            type="primary" 
            icon={<KeyOutlined />} 
            onClick={handleGenerate}
            loading={generating}
            style={{ backgroundColor: '#556b2f' }}
          >
            {t('fieldGenerator.generate')}
          </Button>
        ) : (
          <>
            <Button onClick={() => setGeneratedValues({})}>
              {t('fieldGenerator.cancel')}
            </Button>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={handleGenerate}
              loading={generating}
            >
              {t('fieldGenerator.regenerate')}
            </Button>
            <Button 
              type="primary" 
              onClick={handleApply}
              style={{ backgroundColor: '#556b2f' }}
            >
              {t('fieldGenerator.apply')}
            </Button>
          </>
        )}
      </Space>
    </div>
  )

  return (
    <Popover
      content={popoverContent}
      title={
        <Space>
          <KeyOutlined />
          {t(`fieldGenerator.title.${fieldType}`)}
        </Space>
      }
      trigger="click"
      open={visible}
      onOpenChange={setVisible}
      placement="left"
    >
      <Tooltip title={t('fieldGenerator.tooltip')}>
        <Button 
          type="text" 
          icon={<KeyOutlined />} 
          size="small"
          style={{ color: '#556b2f' }}
        />
      </Tooltip>
    </Popover>
  )
}

export default FieldGenerator