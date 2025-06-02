import React, { useEffect, useState } from 'react'
import { Modal, Button, Space, Checkbox, InputNumber, Alert } from 'antd'
import Editor from '@monaco-editor/react'
import toast from 'react-hot-toast'

interface VaultConfigModalProps {
  open: boolean
  onCancel: () => void
  onSave: (vault: string, version: number) => Promise<void>
  title?: string
  initialVault?: string
  initialVersion?: number
  loading?: boolean
}

const VaultConfigModal: React.FC<VaultConfigModalProps> = ({
  open,
  onCancel,
  onSave,
  title = 'Configure Vault',
  initialVault = '{}',
  initialVersion = 1,
  loading = false,
}) => {
  const [vaultContent, setVaultContent] = useState(initialVault)
  const [vaultVersion, setVaultVersion] = useState(initialVersion)
  const [formatOnSave, setFormatOnSave] = useState(true)
  const [validateOnType, setValidateOnType] = useState(true)
  const [isValid, setIsValid] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setVaultContent(initialVault)
    setVaultVersion(initialVersion)
  }, [initialVault, initialVersion])

  const validateJSON = (content: string) => {
    try {
      JSON.parse(content)
      setIsValid(true)
      setError(null)
      return true
    } catch (e: any) {
      setIsValid(false)
      setError(e.message)
      return false
    }
  }

  const handleEditorChange = (value: string | undefined) => {
    const content = value || '{}'
    setVaultContent(content)
    if (validateOnType) {
      validateJSON(content)
    }
  }

  const handleValidate = () => {
    if (validateJSON(vaultContent)) {
      toast.success('JSON is valid')
    } else {
      toast.error('Invalid JSON')
    }
  }

  const handleSave = async () => {
    if (!validateJSON(vaultContent)) {
      toast.error('Please fix JSON errors before saving')
      return
    }

    let finalContent = vaultContent
    if (formatOnSave) {
      try {
        finalContent = JSON.stringify(JSON.parse(vaultContent), null, 2)
      } catch {
        // Use original if formatting fails
      }
    }

    try {
      await onSave(finalContent, vaultVersion)
      onCancel()
    } catch (error) {
      // Error handled by parent
    }
  }

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onCancel}
      width={800}
      footer={null}
      style={{ top: 20 }}
    >
      <div style={{ marginBottom: 16 }}>
        {!isValid && error && (
          <Alert
            message="JSON Validation Error"
            description={error}
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}
        
        <div className="monaco-editor-container" style={{ height: 400, marginBottom: 16 }}>
          <Editor
            height="100%"
            defaultLanguage="json"
            value={vaultContent}
            onChange={handleEditorChange}
            theme="vs-light"
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              formatOnPaste: true,
              formatOnType: true,
              automaticLayout: true,
            }}
          />
        </div>

        <Space style={{ marginBottom: 16 }}>
          <Checkbox
            checked={formatOnSave}
            onChange={(e) => setFormatOnSave(e.target.checked)}
          >
            Format JSON on save
          </Checkbox>
          <Checkbox
            checked={validateOnType}
            onChange={(e) => setValidateOnType(e.target.checked)}
          >
            Validate on type
          </Checkbox>
        </Space>

        <div style={{ marginBottom: 16 }}>
          <Space>
            <span>Version:</span>
            <InputNumber
              min={1}
              value={vaultVersion}
              onChange={(value) => setVaultVersion(value || 1)}
              style={{ width: 100 }}
            />
            <Checkbox defaultChecked>Auto-increment</Checkbox>
          </Space>
        </div>
      </div>

      <div style={{ textAlign: 'right' }}>
        <Space>
          <Button onClick={handleValidate}>Validate</Button>
          <Button onClick={onCancel}>Cancel</Button>
          <Button
            type="primary"
            onClick={handleSave}
            loading={loading}
            disabled={!isValid}
            style={{ background: '#556b2f', borderColor: '#556b2f' }}
          >
            Save
          </Button>
        </Space>
      </div>
    </Modal>
  )
}

export default VaultConfigModal