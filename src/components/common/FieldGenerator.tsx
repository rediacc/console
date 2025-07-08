import React, { useState } from 'react'
import { Button, Popover, Space, Radio, message, Tooltip } from 'antd'
import { KeyOutlined, ReloadOutlined, CopyOutlined, CheckOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { 
  generateSSHKeyPair, 
  generateRepositoryCredential,
  GenerationOptions 
} from '@/utils/cryptoGenerators'

interface FieldGeneratorProps {
  fieldType: 'ssh_keys' | 'repository_credential'
  onGenerate: (values: Record<string, string>) => void
  entityType?: string
}

const FieldGenerator: React.FC<FieldGeneratorProps> = ({
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

  const generators = {
    ssh_keys: async () => {
      const keys = await generateSSHKeyPair(keyOptions)
      return { SSH_PRIVATE_KEY: keys.privateKey, SSH_PUBLIC_KEY: keys.publicKey }
    },
    repository_credential: () => ({ credential: generateRepositoryCredential() })
  }

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      const values = await generators[fieldType]()
      setGeneratedValues(values)
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
    navigator.clipboard.writeText(value)
      .then(() => {
        setCopiedField(field)
        message.success(t('fieldGenerator.copied'))
        setTimeout(() => setCopiedField(null), 2000)
      })
      .catch(() => message.error(t('fieldGenerator.copyError')))
  }

  const keyTypeOptions = [
    { value: 'rsa', label: 'RSA' },
    { value: 'ed25519', label: `Ed25519 ${t('fieldGenerator.comingSoon')}`, disabled: true }
  ]
  
  const keySizeOptions = [
    { value: 2048, label: '2048 bits' },
    { value: 4096, label: `4096 bits (${t('fieldGenerator.moreSecure')})` }
  ]

  const renderRadioGroup = (label: string, value: any, options: any[], onChange: (val: any) => void) => (
    <div>
      <label style={{ fontWeight: 500 }}>{label}</label>
      <Radio.Group value={value} onChange={(e) => onChange(e.target.value)} style={{ display: 'block', marginTop: 8 }}>
        {options.map(opt => 
          <Radio key={opt.value} value={opt.value} disabled={opt.disabled}>{opt.label}</Radio>
        )}
      </Radio.Group>
    </div>
  )

  const renderSSHKeyOptions = () => (
    <Space direction="vertical" style={{ width: '100%' }}>
      {renderRadioGroup(
        t('fieldGenerator.keyType'), 
        keyOptions.keyType, 
        keyTypeOptions,
        (val) => setKeyOptions({ ...keyOptions, keyType: val })
      )}
      {keyOptions.keyType === 'rsa' && renderRadioGroup(
        t('fieldGenerator.keySize'),
        keyOptions.keySize,
        keySizeOptions,
        (val) => setKeyOptions({ ...keyOptions, keySize: val })
      )}
    </Space>
  )

  const renderGeneratedValues = () => (
    <Space direction="vertical" style={{ width: '100%' }}>
      {Object.entries(generatedValues).map(([field, value]) => (
        <div key={field} style={{ 
          padding: 12, 
          background: 'var(--color-bg-tertiary)', 
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
            background: 'var(--color-bg-primary)',
            border: '1px solid var(--color-border-primary)',
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
            style={{ backgroundColor: 'var(--color-primary)' }}
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
              style={{ backgroundColor: 'var(--color-primary)' }}
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
          style={{ color: 'var(--color-primary)' }}
        />
      </Tooltip>
    </Popover>
  )
}

export default FieldGenerator