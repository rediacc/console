import React, { useState, useEffect } from 'react';
import { Select, Typography, Modal, Form, Input, Space, Button, Spin } from 'antd';
import { ApiOutlined, PlusOutlined, DeleteOutlined, LoadingOutlined } from '@/utils/optimizedIcons';
import { endpointService, Endpoint } from '@/services/endpointService';
import { apiConnectionService } from '@/services/apiConnectionService';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { showMessage } from '@/utils/messages';
import apiClient from '@/api/client';
import axios from 'axios';

const { Option } = Select;
const { Text } = Typography;

interface EndpointHealth {
  isHealthy: boolean;
  version?: string;
  lastChecked: number;
  checking?: boolean;
}

const EndpointSelector: React.FC = () => {
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [customForm] = Form.useForm();
  const [healthStatus, setHealthStatus] = useState<Record<string, EndpointHealth>>({});
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  const HEALTH_CACHE_DURATION = 10000; // 10 seconds

  /**
   * Check health for a single endpoint
   */
  const checkEndpointHealth = async (endpoint: Endpoint): Promise<EndpointHealth> => {
    try {
      const response = await axios.get(`${endpoint.url}/Health`, {
        timeout: 3000,
        validateStatus: (status) => status < 500
      });

      return {
        isHealthy: response.data?.status === 'healthy',
        version: response.data?.version,
        lastChecked: Date.now()
      };
    } catch (error) {
      console.warn(`Health check failed for ${endpoint.name}:`, error);
      return {
        isHealthy: false,
        lastChecked: Date.now()
      };
    }
  };

  /**
   * Check health for all endpoints
   */
  const checkAllEndpointsHealth = async (endpointsList: Endpoint[]) => {
    setIsCheckingHealth(true);
    const healthChecks: Record<string, EndpointHealth> = {};

    // Check health for each endpoint in parallel
    const promises = endpointsList.map(async (endpoint) => {
      // Check if cached health is still valid
      const cached = healthStatus[endpoint.id];
      if (cached && Date.now() - cached.lastChecked < HEALTH_CACHE_DURATION) {
        healthChecks[endpoint.id] = cached;
        return;
      }

      // Set checking state
      healthChecks[endpoint.id] = {
        isHealthy: false,
        checking: true,
        lastChecked: Date.now()
      };

      // Perform health check
      const health = await checkEndpointHealth(endpoint);
      healthChecks[endpoint.id] = health;
    });

    await Promise.all(promises);
    setHealthStatus(healthChecks);
    setIsCheckingHealth(false);
  };

  useEffect(() => {
    const fetchEndpointsAndSelection = async () => {
      try {
        // Fetch all available endpoints
        let allEndpoints = await endpointService.fetchEndpoints();

        // Add dynamic endpoint based on current domain (if not already present)
        const currentOrigin = window.location.origin;
        const currentDomain = window.location.hostname;

        // Only add dynamic endpoint if:
        // 1. Not localhost (we already have localhost endpoint)
        // 2. Not already in the list
        if (currentDomain !== 'localhost' && currentDomain !== '127.0.0.1') {
          const dynamicApiUrl = `${currentOrigin}/api`;

          // Check if this URL already exists
          const existingEndpoint = allEndpoints.find(e => e.url === dynamicApiUrl);

          if (!existingEndpoint) {
            // Add dynamic endpoint
            const dynamicEndpoint: Endpoint = {
              id: 'dynamic-current-domain',
              name: 'Current Domain',
              url: dynamicApiUrl,
              type: 'dynamic',
              description: `API at ${currentDomain}`,
              icon: '🌍'
            };

            // Add at the beginning of the list (after production/sandbox if they exist)
            allEndpoints = [...allEndpoints, dynamicEndpoint];
          }
        }

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
        } else if (!selected) {
          // For non-localhost domains, if no saved selection exists, check and auto-select dynamic endpoint
          const dynamicEndpoint = allEndpoints.find(e => e.type === 'dynamic');
          if (dynamicEndpoint) {
            // Check if dynamic endpoint is healthy
            const health = await checkEndpointHealth(dynamicEndpoint);
            if (health.isHealthy) {
              selected = dynamicEndpoint;
              endpointService.setSelectedEndpoint(dynamicEndpoint);
              console.log(`[EndpointSelector] Auto-selected healthy dynamic endpoint: ${dynamicEndpoint.url}`);
            } else {
              console.log(`[EndpointSelector] Dynamic endpoint is not healthy, skipping auto-selection`);
            }
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
          console.log(`[EndpointSelector] Applied endpoint: ${selected.name} (${selected.url})`);
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
          onDropdownVisibleChange={(open) => {
            if (open && endpoints.length > 0) {
              // Check health when dropdown opens
              checkAllEndpointsHealth(endpoints);
            }
          }}
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
        {endpoints.map((endpoint) => {
          const health = healthStatus[endpoint.id];
          const isHealthy = health?.isHealthy || endpoint.type === 'localhost'; // Always show localhost as healthy
          const isChecking = health?.checking;
          const isDisabled = !isHealthy && endpoint.type !== 'localhost'; // Never disable localhost

          // Label for selected value (with health indicator but without version)
          const labelContent = (
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {isChecking ? (
                <LoadingOutlined style={{ fontSize: 10, color: 'var(--color-warning)' }} />
              ) : (
                <span style={{
                  fontSize: 10,
                  color: isHealthy ? 'var(--color-success)' : 'var(--color-error)'
                }}>
                  ●
                </span>
              )}
              <span>
                {endpoint.icon && `${endpoint.icon} `}
                {endpoint.name}
              </span>
            </span>
          );

          return (
            <Option
              key={endpoint.id}
              value={endpoint.id}
              data-testid={`endpoint-option-${endpoint.id}`}
              disabled={isDisabled}
              label={labelContent}
            >
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
                gap: 8
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {/* Health indicator */}
                  {isChecking ? (
                    <LoadingOutlined style={{ fontSize: 10, color: 'var(--color-warning)' }} />
                  ) : (
                    <span style={{
                      fontSize: 10,
                      color: isHealthy ? 'var(--color-success)' : 'var(--color-error)'
                    }}>
                      {isHealthy ? '●' : '●'}
                    </span>
                  )}

                  <span style={{ opacity: isDisabled ? 0.5 : 1 }}>
                    {endpoint.icon && `${endpoint.icon} `}
                    {endpoint.name}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
                  {/* Version display */}
                  {health?.version && (
                    <span style={{
                      fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
                      color: 'var(--color-text-quaternary)',
                      opacity: 0.7
                    }}>
                      v{health.version}
                    </span>
                  )}

                  {/* Delete button for custom endpoints */}
                  {endpoint.type === 'custom' && (
                    <DeleteOutlined
                      style={{
                        fontSize: DESIGN_TOKENS.FONT_SIZE.XS,
                        color: 'var(--color-error)',
                      }}
                      onClick={(e) => handleRemoveCustomEndpoint(endpoint.id, e)}
                    />
                  )}
                </div>
              </div>
            </Option>
          );
        })}

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
          {isCheckingHealth && (
            <span style={{ marginLeft: 8 }}>
              <LoadingOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS }} />
            </span>
          )}
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
