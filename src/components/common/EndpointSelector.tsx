import React, { useState, useEffect } from 'react';
import { Select, Typography, Modal, Form, Input, Space, Button } from 'antd';
import { ApiOutlined, PlusOutlined, DeleteOutlined } from '@/utils/optimizedIcons';
import { endpointService, Endpoint } from '@/services/endpointService';
import { apiConnectionService } from '@/services/apiConnectionService';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { showMessage } from '@/utils/messages';
import apiClient from '@/api/client';

const { Option } = Select;
const { Text } = Typography;

const EndpointSelector: React.FC = () => {
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [customForm] = Form.useForm();

  useEffect(() => {
    const fetchEndpointsAndSelection = async () => {
      try {
        // Fetch all available endpoints
        const allEndpoints = await endpointService.fetchEndpoints();
        setEndpoints(allEndpoints);

        // Get currently selected endpoint or determine from connection service
        let selected = endpointService.getSelectedEndpoint();

        // ALWAYS auto-select localhost when running locally (takes precedence over saved selection)
        if (endpointService.isLocalhost()) {
          const localhostEndpoint = allEndpoints.find(e => e.type === 'localhost');
          if (localhostEndpoint) {
            selected = localhostEndpoint;
            endpointService.setSelectedEndpoint(localhostEndpoint);
          }
        }

        // If no selection (not localhost), get from connection service
        if (!selected) {
          const connectionInfo = apiConnectionService.getSelectedEndpoint();
          if (connectionInfo) {
            selected = allEndpoints.find(e => e.url === connectionInfo.url) || null;
          }
        }

        setSelectedEndpoint(selected);

        // If we have a selected endpoint, update the API client immediately
        if (selected) {
          apiClient.updateApiUrl(selected.url);
          console.log(`[EndpointSelector] Applied saved endpoint: ${selected.name} (${selected.url})`);
        }
      } catch (error) {
        console.warn('Failed to fetch endpoints', error);
      } finally {
        setLoading(false);
      }
    };

    fetchEndpointsAndSelection();
  }, []);

  const handleEndpointChange = async (value: string) => {
    if (value === '__add_custom__') {
      setShowCustomModal(true);
      return;
    }

    const endpoint = endpoints.find(e => e.id === value);
    if (!endpoint) return;

    // Save selection
    endpointService.setSelectedEndpoint(endpoint);
    setSelectedEndpoint(endpoint);

    // Update API client with new endpoint
    apiClient.updateApiUrl(endpoint.url);

    showMessage('success', `Switched to ${endpoint.name}`);
  };

  const handleAddCustomEndpoint = async (values: { name: string; url: string }) => {
    try {
      const newEndpoint = await endpointService.addCustomEndpoint(values.name, values.url);

      // Refresh endpoints list
      const allEndpoints = await endpointService.fetchEndpoints(true);
      setEndpoints(allEndpoints);

      // Select the new custom endpoint
      endpointService.setSelectedEndpoint(newEndpoint);
      setSelectedEndpoint(newEndpoint);

      // Update API client
      apiClient.updateApiUrl(newEndpoint.url);

      showMessage('success', `Added and selected ${newEndpoint.name}`);
      setShowCustomModal(false);
      customForm.resetFields();
    } catch (error: any) {
      showMessage('error', error.message || 'Failed to add custom endpoint');
    }
  };

  const handleRemoveCustomEndpoint = (endpointId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent dropdown from closing

    Modal.confirm({
      title: 'Remove Custom Endpoint',
      content: 'Are you sure you want to remove this custom endpoint?',
      onOk: async () => {
        endpointService.removeCustomEndpoint(endpointId);

        // Refresh endpoints list
        const allEndpoints = await endpointService.fetchEndpoints(true);
        setEndpoints(allEndpoints);

        // If removed endpoint was selected, clear selection
        if (selectedEndpoint?.id === endpointId) {
          setSelectedEndpoint(null);
        }

        showMessage('success', 'Custom endpoint removed');
      }
    });
  };

  // Show loading state
  if (loading) {
    return (
      <Text type="secondary" style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS, opacity: 0.6 }}>
        Loading...
      </Text>
    );
  }

  // If no endpoint selected and we have endpoints, show the first one
  const displayValue = selectedEndpoint?.id || endpoints[0]?.id;

  return (
    <>
      <div style={{ display: 'inline-block' }}>
        <Select
          value={displayValue}
          onChange={handleEndpointChange}
          style={{
            fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
            width: 200
          }}
          size="small"
          suffixIcon={<ApiOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS }} />}
          popupMatchSelectWidth={false}
          data-testid="endpoint-selector"
          dropdownStyle={{
            fontSize: DESIGN_TOKENS.FONT_SIZE.XS
          }}
        >
        {/* Predefined and custom endpoints */}
        {endpoints.map((endpoint) => (
          <Option key={endpoint.id} value={endpoint.id} data-testid={`endpoint-option-${endpoint.id}`}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: DESIGN_TOKENS.FONT_SIZE.XS
            }}>
              <span>
                {endpoint.icon && `${endpoint.icon} `}
                {endpoint.name}
              </span>
              {endpoint.type === 'custom' && (
                <DeleteOutlined
                  style={{
                    fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
                    color: 'var(--color-error)',
                    marginLeft: 8
                  }}
                  onClick={(e) => handleRemoveCustomEndpoint(endpoint.id, e)}
                />
              )}
            </div>
          </Option>
        ))}

        {/* Add custom endpoint option */}
        <Option key="__add_custom__" value="__add_custom__" data-testid="endpoint-option-add-custom">
          <span style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS, color: 'var(--color-primary)' }}>
            <PlusOutlined /> Add Custom Endpoint...
          </span>
        </Option>
      </Select>

      {/* Display selected endpoint URL */}
      {selectedEndpoint && (
        <div style={{
          fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
          color: 'var(--color-text-tertiary)',
          marginTop: 4,
          textAlign: 'center'
        }}>
          {selectedEndpoint.url}
        </div>
      )}
    </div>

      {/* Add Custom Endpoint Modal */}
      <Modal
        title="Add Custom Endpoint"
        open={showCustomModal}
        onCancel={() => {
          setShowCustomModal(false);
          customForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={customForm}
          layout="vertical"
          onFinish={handleAddCustomEndpoint}
        >
          <Form.Item
            name="name"
            label="Endpoint Name"
            rules={[
              { required: true, message: 'Please enter a name for this endpoint' },
              { min: 2, message: 'Name must be at least 2 characters' }
            ]}
          >
            <Input
              placeholder="e.g., Staging Server"
              data-testid="custom-endpoint-name-input"
            />
          </Form.Item>

          <Form.Item
            name="url"
            label="API URL"
            rules={[
              { required: true, message: 'Please enter the API URL' },
              {
                pattern: /^https?:\/\/.+/,
                message: 'URL must start with http:// or https://'
              }
            ]}
            extra="The URL will be normalized to end with /api if not already"
          >
            <Input
              placeholder="https://api.example.com"
              data-testid="custom-endpoint-url-input"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setShowCustomModal(false);
                customForm.resetFields();
              }}>
                Cancel
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                data-testid="custom-endpoint-submit-button"
              >
                Add Endpoint
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default EndpointSelector;
