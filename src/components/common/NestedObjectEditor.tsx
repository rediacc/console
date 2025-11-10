import React, { useState } from 'react'
import {
  Form,
  Input,
  Button,
  Switch,
  Space,
  Card,
  Collapse,
  Typography,
  Popconfirm,
  Tag,
  Empty,
  Row,
  Col,
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  CodeOutlined,
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { SimpleJsonEditor } from './SimpleJsonEditor'

const { Text, Title } = Typography
const { Panel } = Collapse

interface NestedObjectEditorProps {
  value?: Record<string, any>
  onChange?: (value: Record<string, any>) => void
  fieldDefinition?: {
    properties?: Record<string, any>
    additionalProperties?: boolean | Record<string, any>
  }
  readOnly?: boolean
  title?: string
  description?: string
  'data-testid'?: string
}

interface ObjectEntry {
  key: string
  value: any
  isEditing?: boolean
}

// Helper function to detect structure patterns
const detectStructurePattern = (obj: Record<string, any>): {
  isUniform: boolean
  keys?: string[]
  hasImagePattern?: boolean
} => {
  const entries = Object.entries(obj)
  if (entries.length === 0) return { isUniform: false }

  // Check if all values have the same structure
  const firstValue = entries[0][1]
  if (typeof firstValue !== 'object' || Array.isArray(firstValue)) return { isUniform: false }

  const firstKeys = Object.keys(firstValue).sort()
  
  // Check if all entries have the same keys
  const isConsistent = entries.every(([_, value]) => {
    if (typeof value !== 'object' || Array.isArray(value)) return false
    const keys = Object.keys(value).sort()
    return keys.length === firstKeys.length && keys.every((k, i) => k === firstKeys[i])
  })

  if (!isConsistent) return { isUniform: false }

  // Check for image-like patterns
  let hasImagePattern = false
  if (firstKeys.includes('image')) {
    hasImagePattern = entries.some(([_, value]) => {
      const image = value.image
      return typeof image === 'string' && (image.includes(':') || image.includes('/'))
    })
  }

  return { 
    isUniform: true, 
    keys: firstKeys,
    hasImagePattern
  }
}

export const NestedObjectEditor: React.FC<NestedObjectEditorProps> = ({
  value = {},
  onChange,
  fieldDefinition,
  readOnly = false,
  title,
  description,
  'data-testid': dataTestId,
}) => {
  const { t } = useTranslation('common')
  const [entries, setEntries] = useState<ObjectEntry[]>(() =>
    Object.entries(value).map(([key, val]) => ({
      key,
      value: val,
      isEditing: false,
    }))
  )
  const [newKey, setNewKey] = useState('')
  const [showRawJson, setShowRawJson] = useState(false)
  const [rawJsonValue, setRawJsonValue] = useState(() => JSON.stringify(value, null, 2))
  const [rawJsonError, setRawJsonError] = useState<string | null>(null)
  const [structureInfo, setStructureInfo] = useState<ReturnType<typeof detectStructurePattern>>(() => detectStructurePattern(value))

  // Sync state with props when value changes
  React.useEffect(() => {
    const entriesArray = Object.entries(value).map(([key, val]) => ({
      key,
      value: val,
      isEditing: false,
    }))
    setEntries(entriesArray)
    setRawJsonValue(JSON.stringify(value, null, 2))

    // Detect pattern in the data
    const info = detectStructurePattern(value)
    setStructureInfo(info)
  }, [value])

  // Convert entries back to object and notify parent
  const updateValue = (newEntries: ObjectEntry[]) => {
    const newValue = newEntries.reduce((acc, entry) => {
      acc[entry.key] = entry.value
      return acc
    }, {} as Record<string, any>)
    
    setEntries(newEntries)
    setRawJsonValue(JSON.stringify(newValue, null, 2))
    onChange?.(newValue)
  }

  const handleAddEntry = () => {
    if (!newKey.trim()) return

    // Check if key already exists
    if (entries.some(e => e.key === newKey)) {
      // You could show an error message here
      return
    }

    // Determine default value based on detected pattern or fieldDefinition
    let defaultValue: any = ''
    
    // Use detected pattern to create appropriate default
    if (structureInfo.isUniform && structureInfo.keys && entries.length > 0) {
      // Copy structure from existing entries
      const firstEntry = entries[0]
      if (typeof firstEntry.value === 'object' && !Array.isArray(firstEntry.value)) {
        // Create new object with same keys but smart default values
        defaultValue = Object.keys(firstEntry.value).reduce((acc, key) => {
          const existingValue = firstEntry.value[key]
          
          // Special handling for common field names
          if (key === 'active' || key === 'enabled') {
            acc[key] = true  // Default to enabled
          } else if (key === 'image' && structureInfo.hasImagePattern) {
            acc[key] = ''  // Empty string for image paths
          } else if (typeof existingValue === 'boolean') {
            acc[key] = false
          } else if (typeof existingValue === 'number') {
            acc[key] = 0
          } else if (typeof existingValue === 'string') {
            acc[key] = ''
          } else if (Array.isArray(existingValue)) {
            acc[key] = []
          } else if (typeof existingValue === 'object') {
            acc[key] = {}
          } else {
            acc[key] = ''
          }
          return acc
        }, {} as Record<string, any>)
      }
    } else if (fieldDefinition?.additionalProperties && typeof fieldDefinition.additionalProperties === 'object') {
      const propDef = fieldDefinition.additionalProperties
      if (propDef.type === 'object' && propDef.properties) {
        // Create default object based on properties
        defaultValue = Object.keys(propDef.properties).reduce((acc, key) => {
          const fieldDef = propDef.properties[key]
          acc[key] = fieldDef.default ?? (fieldDef.type === 'boolean' ? false : '')
          return acc
        }, {} as Record<string, any>)
      } else if (propDef.type === 'boolean') {
        defaultValue = false
      } else if (propDef.type === 'number') {
        defaultValue = 0
      }
    }

    const newEntries = [...entries, { key: newKey, value: defaultValue, isEditing: true }]
    updateValue(newEntries)
    setNewKey('')
  }

  const handleDeleteEntry = (index: number) => {
    const newEntries = entries.filter((_, i) => i !== index)
    updateValue(newEntries)
  }

  const handleUpdateEntry = (index: number, updates: Partial<ObjectEntry>) => {
    const newEntries = [...entries]
    newEntries[index] = { ...newEntries[index], ...updates }
    updateValue(newEntries)
  }

  const handleRawJsonChange = (jsonString: string) => {
    setRawJsonValue(jsonString)
    try {
      const parsed = JSON.parse(jsonString)
      setRawJsonError(null)
      onChange?.(parsed)
    } catch (e) {
      setRawJsonError((e as Error).message)
    }
  }

  const renderEntryValue = (entry: ObjectEntry, index: number) => {
    const entryDef = fieldDefinition?.properties?.[entry.key] || fieldDefinition?.additionalProperties

    // For structures with uniform object values
    if (typeof entry.value === 'object' && !Array.isArray(entry.value)) {
      // Render special UI for known field patterns
      const hasImageAndActive = Object.prototype.hasOwnProperty.call(entry.value, 'image') && Object.prototype.hasOwnProperty.call(entry.value, 'active')
      const isImageLike = typeof entry.value.image === 'string' && 
        (entry.value.image.includes(':') || entry.value.image.includes('/'))
      
      if (hasImageAndActive && (structureInfo.hasImagePattern || isImageLike)) {
        return (
          <Card 
            size="small" 
            style={{ 
              marginTop: 'var(--space-sm)', 
              backgroundColor: 'var(--color-bg-tertiary)',
              border: '1px solid var(--color-border-secondary)',
              borderRadius: '8px',
              boxShadow: 'var(--shadow-sm)'
            }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Row gutter={16}>
                <Col span={18}>
                  <Form.Item 
                    label={
                      <Text strong style={{ fontSize: '13px', color: 'var(--color-text)' }}>
                        {t('nestedObjectEditor.Image')}
                      </Text>
                    } 
                    style={{ marginBottom: 'var(--space-sm)' }}
                  >
                    <Input
                      value={entry.value.image}
                      onChange={(e) => handleUpdateEntry(index, {
                        value: { ...entry.value, image: e.target.value }
                      })}
                      disabled={readOnly}
                      placeholder="e.g., registry/image:tag"
                      data-testid={dataTestId ? `${dataTestId}-field-${entry.key}-image` : `vault-editor-nested-field-${entry.key}-image`}
                    />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item 
                    label={
                      <Text strong style={{ fontSize: '13px', color: 'var(--color-text)' }}>
                        {t('nestedObjectEditor.Active')}
                      </Text>
                    } 
                    style={{ marginBottom: 'var(--space-sm)' }}
                  >
                    <Switch
                      checked={entry.value.active}
                      onChange={(checked) => handleUpdateEntry(index, {
                        value: { ...entry.value, active: checked }
                      })}
                      disabled={readOnly}
                      data-testid={dataTestId ? `${dataTestId}-field-${entry.key}-active` : `vault-editor-nested-field-${entry.key}-active`}
                    />
                  </Form.Item>
                </Col>
              </Row>
            </Space>
          </Card>
        )
      }

      // Generic object rendering
      return (
        <NestedObjectEditor
          value={entry.value}
          onChange={(newValue) => handleUpdateEntry(index, { value: newValue })}
          fieldDefinition={entryDef}
          readOnly={readOnly}
          data-testid={dataTestId ? `${dataTestId}-nested-${entry.key}` : `vault-editor-nested-nested-${entry.key}`}
        />
      )
    }

    // Simple value types
    if (typeof entry.value === 'boolean') {
      return (
        <Switch
          checked={entry.value}
          onChange={(checked) => handleUpdateEntry(index, { value: checked })}
          disabled={readOnly}
          data-testid={dataTestId ? `${dataTestId}-field-${entry.key}` : `vault-editor-nested-field-${entry.key}`}
        />
      )
    }

    if (typeof entry.value === 'number') {
      return (
        <Input
          type="number"
          value={entry.value}
          onChange={(e) => handleUpdateEntry(index, { value: Number(e.target.value) })}
          disabled={readOnly}
          style={{ width: '100%', maxWidth: '200px' }}
          data-testid={dataTestId ? `${dataTestId}-field-${entry.key}` : `vault-editor-nested-field-${entry.key}`}
        />
      )
    }

    // Default to string input
    return (
      <Input
        value={entry.value}
        onChange={(e) => handleUpdateEntry(index, { value: e.target.value })}
        disabled={readOnly}
        data-testid={dataTestId ? `${dataTestId}-field-${entry.key}` : `vault-editor-nested-field-${entry.key}`}
      />
    )
  }

  return (
    <div>
      {(title || description || structureInfo.isUniform) && (
        <div style={{ 
          marginBottom: 'var(--space-md)', 
          padding: 'var(--space-md)', 
          backgroundColor: 'var(--color-bg-tertiary)', 
          borderRadius: '8px', 
          border: '1px solid var(--color-border-secondary)',
          boxShadow: 'var(--shadow-sm)'
        }}>
          {title && <Title level={5} style={{ 
            margin: 0, 
            marginBottom: 'var(--space-xs)', 
            color: 'var(--color-text-primary)', 
            fontWeight: 600 
          }}>{title}</Title>}
          {description && (
            <Text type="secondary" style={{ fontSize: '14px', lineHeight: '1.5' }}>
              <InfoCircleOutlined style={{ marginRight: 'var(--space-xs)', color: 'var(--color-primary)' }} /> {description}
            </Text>
          )}
          {structureInfo.isUniform && (
            <div style={{ marginTop: 'var(--space-sm)' }}>
              <Space>
                <Tag color="success" style={{ fontWeight: 500 }}>
                  {t('nestedObjectEditor.Uniform Structure')}
                </Tag>
                {structureInfo.keys && (
                  <Text type="secondary" style={{ fontSize: '12px', fontFamily: 'monospace', backgroundColor: 'var(--color-fill-quaternary)', padding: '2px 6px', borderRadius: '4px' }}>
                    {t('nestedObjectEditor.Fields')}: {structureInfo.keys.join(', ')}
                  </Text>
                )}
                {structureInfo.hasImagePattern && (
                  <Tag color="processing" style={{ fontWeight: 500 }}>
                    {t('nestedObjectEditor.Container Images Detected')}
                  </Tag>
                )}
              </Space>
            </div>
          )}
        </div>
      )}

      <Space direction="vertical" style={{ width: '100%' }}>
        {!readOnly && (
          <Card 
            size="small" 
            style={{ 
              backgroundColor: 'var(--color-bg-secondary)', 
              border: '1px solid var(--color-border-primary)',
              borderRadius: '8px',
              marginBottom: 'var(--space-md)',
              boxShadow: 'var(--shadow-sm)'
            }}
            title={
              <Text strong style={{ color: 'var(--color-text-primary)', fontSize: '14px' }}>
                {t('nestedObjectEditor.Add New Entry')}
              </Text>
            }
          >
            <Space.Compact style={{ width: '100%' }}>
              <Input
                placeholder={t('nestedObjectEditor.Enter key name')}
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                onPressEnter={handleAddEntry}
                style={{ width: '70%', fontSize: '14px' }}
                autoComplete="off"
                data-testid={dataTestId ? `${dataTestId}-new-key` : 'vault-editor-nested-new-key'}
              />
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleAddEntry}
                disabled={!newKey.trim()}
                style={{ fontWeight: 500, minHeight: '36px' }}
                data-testid={dataTestId ? `${dataTestId}-add` : 'vault-editor-nested-add'}
              >
                {t('nestedObjectEditor.Add')}
              </Button>
              <Button
                icon={<CodeOutlined />}
                onClick={() => setShowRawJson(!showRawJson)}
                style={{ minHeight: '36px' }}
                data-testid={dataTestId ? `${dataTestId}-toggle-json` : 'vault-editor-nested-toggle-json'}
              >
                {showRawJson ? t('nestedObjectEditor.Hide JSON') : t('nestedObjectEditor.Show JSON')}
              </Button>
            </Space.Compact>
          </Card>
        )}

        {entries.length === 0 ? (
          <Empty
            description={t('nestedObjectEditor.No entries')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Collapse 
            defaultActiveKey={entries.map((_, i) => i.toString())} 
            style={{ 
              backgroundColor: 'transparent',
              border: 'none'
            }}
            data-testid={dataTestId ? `${dataTestId}-collapse` : 'vault-editor-nested-collapse'}
          >
            {entries.map((entry, index) => (
              <Panel
                key={index}
                data-testid={dataTestId ? `${dataTestId}-panel-${entry.key}` : `vault-editor-nested-panel-${entry.key}`}
                header={
                  <Space style={{ alignItems: 'center' }}>
                    <Tag 
                      color="processing" 
                      style={{ 
                        fontFamily: 'monospace', 
                        fontWeight: 600,
                        fontSize: '13px',
                        padding: '4px 8px'
                      }}
                    >
                      {entry.key}
                    </Tag>
                    {typeof entry.value === 'object' && !Array.isArray(entry.value) && (
                      <Tag color="success" style={{ fontSize: '11px', fontWeight: 500 }}>
                        {t('nestedObjectEditor.Object')}
                      </Tag>
                    )}
                    {Array.isArray(entry.value) && (
                      <Tag color="warning" style={{ fontSize: '11px', fontWeight: 500 }}>
                        {t('nestedObjectEditor.Array')}
                      </Tag>
                    )}
                    {typeof entry.value === 'boolean' && (
                      <Tag 
                        color={entry.value ? 'success' : 'default'} 
                        style={{ fontSize: '11px', fontWeight: 500 }}
                      >
                        {entry.value ? t('nestedObjectEditor.True') : t('nestedObjectEditor.False')}
                      </Tag>
                    )}
                  </Space>
                }
                extra={
                  !readOnly && (
                    <Space onClick={(e) => e.stopPropagation()}>
                      <Popconfirm
                        title={t('nestedObjectEditor.Delete this entry?')}
                        onConfirm={() => handleDeleteEntry(index)}
                        okText={t('nestedObjectEditor.Yes')}
                        cancelText={t('nestedObjectEditor.No')}
                      >
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          size="small"
                          data-testid={dataTestId ? `${dataTestId}-delete-${entry.key}` : `vault-editor-nested-delete-${entry.key}`}
                        />
                      </Popconfirm>
                    </Space>
                  )
                }
              >
                {renderEntryValue(entry, index)}
              </Panel>
            ))}
          </Collapse>
        )}

        {showRawJson && (
          <Card 
            title={
              <Text strong style={{ color: 'var(--color-text-primary)', fontSize: '14px' }}>
                <CodeOutlined style={{ marginRight: 'var(--space-xs)' }} />
                {t('nestedObjectEditor.Raw JSON Editor')}
              </Text>
            }
            size="small"
            style={{
              backgroundColor: 'var(--color-bg-secondary)',
              border: '1px solid var(--color-border-primary)',
              borderRadius: '8px',
              marginTop: 'var(--space-md)',
              boxShadow: 'var(--shadow-sm)'
            }}
          >
            {rawJsonError && (
              <Text type="danger" style={{ display: 'block', marginBottom: 8 }}>
                {t('nestedObjectEditor.JSON Error')}: {rawJsonError}
              </Text>
            )}
            <SimpleJsonEditor
              value={rawJsonValue}
              onChange={handleRawJsonChange}
              readOnly={readOnly}
              height="300px"
              data-testid={dataTestId ? `${dataTestId}-raw-json` : 'vault-editor-nested-raw-json'}
            />
          </Card>
        )}
      </Space>
    </div>
  )
}