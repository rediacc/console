import React, { useState } from 'react'
import { Button, Popover, Space, Radio, message, Tooltip } from 'antd'
import { KeyOutlined, ReloadOutlined, CopyOutlined, CheckOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { 
  generateSSHKeyPair, 
  generateRepositoryCredential,
  GenerationOptions 
} from '@/utils/cryptoGenerators'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius, fontSize } from '@/utils/styleConstants'

interface FieldGeneratorProps {
  fieldType: 'ssh_keys' | 'repository_credential'
  onGenerate: (values: Record<string, string>) => void
  entityType?: string
  'data-testid'?: string
}

const FieldGenerator: React.FC<FieldGeneratorProps> = (props) => {
  const {
    fieldType,
    onGenerate,
    entityType
  } = props
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
  const styles = useComponentStyles()

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
        // Reset copy state immediately after user interaction
        setCopiedField(null)
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
      <label style={{ 
        fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM,
        fontSize: fontSize('SM'),
        display: 'block',
        marginBottom: spacing('XS')
      }}>{label}</label>
      <Radio.Group 
        value={value} 
        onChange={(e) => onChange(e.target.value)} 
        style={{ 
          display: 'block', 
          marginTop: spacing('XS') 
        }} 
        data-testid={`vault-editor-radio-${label.toLowerCase().replace(/\s+/g, '-')}`}
      >
        {options.map(opt => 
          <Radio 
            key={opt.value} 
            value={opt.value} 
            disabled={opt.disabled} 
            style={{
              fontSize: fontSize('SM'),
              marginBottom: spacing('XS')
            }}
            data-testid={`vault-editor-radio-option-${opt.value}`}
          >
            {opt.label}
          </Radio>
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
          padding: spacing('SM'), 
          background: 'var(--color-fill-quaternary)', 
          borderRadius: borderRadius('MD'),
          fontFamily: 'monospace',
          fontSize: fontSize('XS')
        }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center', 
            marginBottom: spacing('XS') 
          }}>
            <strong style={{ fontSize: fontSize('SM') }}>{field}:</strong>
            <Button
              size="small"
              icon={copiedField === field ? 
                <CheckOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} /> : 
                <CopyOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />
              }
              onClick={() => handleCopy(field, value)}
              style={{
                minHeight: DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT_SM,
                borderRadius: borderRadius('SM'),
                fontSize: fontSize('XS')
              }}
              data-testid={`vault-editor-copy-${field.toLowerCase()}`}
            >
              {copiedField === field ? t('fieldGenerator.copied') : t('fieldGenerator.copy')}
            </Button>
          </div>
          <div style={{
            wordBreak: 'break-all',
            maxHeight: 100,
            overflow: 'auto',
            padding: spacing('SM'),
            background: 'var(--color-bg-primary)',
            border: '1px solid var(--color-border-secondary)',
            borderRadius: borderRadius('SM'),
            fontSize: fontSize('XS'),
            lineHeight: DESIGN_TOKENS.LINE_HEIGHT.NORMAL
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
      
      <Space style={{ 
        marginTop: spacing('MD'), 
        width: '100%', 
        justifyContent: 'flex-end' 
      }}>
        {Object.keys(generatedValues).length === 0 ? (
          <Button 
            type="primary" 
            icon={<KeyOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />} 
            onClick={handleGenerate}
            loading={generating}
            style={{ 
              ...styles.buttonPrimary,
              backgroundColor: 'var(--color-primary)',
              minHeight: DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT
            }}
            data-testid="vault-editor-generate-button"
          >
            {t('fieldGenerator.generate')}
          </Button>
        ) : (
          <>
            <Button 
              onClick={() => setGeneratedValues({})} 
              style={{
                minHeight: DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT,
                borderRadius: borderRadius('LG'),
                fontSize: fontSize('SM')
              }}
              data-testid="vault-editor-generate-cancel"
            >
              {t('fieldGenerator.cancel')}
            </Button>
            <Button 
              icon={<ReloadOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />} 
              onClick={handleGenerate}
              loading={generating}
              style={{
                minHeight: DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT,
                borderRadius: borderRadius('LG'),
                fontSize: fontSize('SM')
              }}
              data-testid="vault-editor-regenerate-button"
            >
              {t('fieldGenerator.regenerate')}
            </Button>
            <Button 
              type="primary" 
              onClick={handleApply}
              style={{ 
                ...styles.buttonPrimary,
                backgroundColor: 'var(--color-primary)',
                minHeight: DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT
              }}
              data-testid="vault-editor-apply-generated"
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
          <KeyOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />
          <span style={{ fontSize: fontSize('SM') }}>{t(`fieldGenerator.title.${fieldType}`)}</span>
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
          icon={<KeyOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />} 
          size="small"
          style={{ 
            color: 'var(--color-primary)',
            minHeight: DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT_SM,
            minWidth: DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT_SM,
            borderRadius: borderRadius('SM')
          }}
          data-testid={props['data-testid'] || 'vault-editor-field-generator'}
        />
      </Tooltip>
    </Popover>
  )
}

export default FieldGenerator