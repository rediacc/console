import React, { useState, useEffect } from 'react';
import { Modal, Form, Input, Space, Button } from 'antd';
import { ApiOutlined, PlusOutlined, DeleteOutlined, LoadingOutlined } from '@/utils/optimizedIcons';
import { endpointService, Endpoint } from '@/services/endpointService';
import { apiConnectionService } from '@/services/apiConnectionService';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { showMessage } from '@/utils/messages';
import apiClient from '@/api/client';
import axios from 'axios';
import {
  StyledSelect,
  LoadingText,
  EndpointUrlText,
  OptionWrapper,
  OptionLeft,
  OptionRight,
  HealthIndicator,
  EndpointName,
  VersionLabel,
  EmojiIcon,
  LabelContent,
  AddCustomOption,
  EndpointNameText
} from './styles';

const { Option } = StyledSelect;

interface EndpointHealth {
  isHealthy: boolean;
  version?: string;
  lastChecked: number;
  checking?: boolean;
}

interface EndpointSelectorProps {
  onHealthCheckComplete?: (hasHealthyEndpoint: boolean) => void;
}

const EndpointSelector: React.FC<EndpointSelectorProps> = ({
  onHealthCheckComplete
}) => {
  const [modal, contextHolder] = Modal.useModal();
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [customForm] = Form.useForm();
  const [healthStatus, setHealthStatus] = useState<Record<string, EndpointHealth>>({});
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  const HEALTH_CACHE_DURATION = 10000; // 10 seconds
  const HEALTH_CHECK_TIMEOUT = 2500; // 2.5 seconds

  /**
   * Check health for a single endpoint
   */
  const checkEndpointHealth = async (endpoint: Endpoint): Promise<EndpointHealth> => {
    try {
      const response = await axios.get(`${endpoint.url}/Health`, {
        timeout: HEALTH_CHECK_TIMEOUT,
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
  const checkAllEndpointsHealth = async (endpointsList: Endpoint[]): Promise<Record<string, EndpointHealth>> => {
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

    return healthChecks;
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

        // Run health checks on all endpoints
        const healthChecks = await checkAllEndpointsHealth(allEndpoints);

        // Get currently selected endpoint or determine from connection service
        let selected = endpointService.getSelectedEndpoint();

        // Auto-select localhost when running locally ONLY if no endpoint is already selected
        if (endpointService.isLocalhost() && !selected) {
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

        // Notify parent about health check completion
        if (onHealthCheckComplete) {
          const hasHealthyEndpoint = Object.values(healthChecks).some(h => h.isHealthy);
          onHealthCheckComplete(hasHealthyEndpoint);
        }
      } catch (error) {
        console.warn('Failed to fetch endpoints', error);
      } finally {
        setLoading(false);
      }
    };

    fetchEndpointsAndSelection();
  }, [onHealthCheckComplete]);

  const handleEndpointChange = async (value: unknown) => {
    const endpointValue = value as string;
    if (endpointValue === '__add_custom__') {
      setShowCustomModal(true);
      return;
    }

    const endpoint = endpoints.find(e => e.id === endpointValue);
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

    modal.confirm({
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
      <LoadingText type="secondary">
        Loading...
      </LoadingText>
    );
  }

  // If no endpoint selected and we have endpoints, show the first one
  const displayValue = selectedEndpoint?.id || endpoints[0]?.id;

  return (
    <>
      <div style={{ display: 'inline-block' }}>
        <StyledSelect
          value={displayValue}
          onChange={handleEndpointChange}
          // onDropdownVisibleChange={(open) => {
          //   if (open && endpoints.length > 0) {
          //     // Check health when dropdown opens
          //     checkAllEndpointsHealth(endpoints);
          //   }
          // }}
          size="small"
          suffixIcon={<ApiOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XL, alignSelf: 'flex-end' }} />}
          popupMatchSelectWidth={false}
          data-testid="endpoint-selector"
        >
        {/* Predefined and custom endpoints */}
        {endpoints.map((endpoint) => {
          const health = healthStatus[endpoint.id];
          // Default to unhealthy until proven otherwise (pessimistic approach)
          const isHealthy = health?.isHealthy ?? false;
          const isChecking = health?.checking;
          // Disable if not checked yet or unhealthy (except localhost which is always enabled)
          const isDisabled = (!health || (!health.isHealthy && !health.checking)) && endpoint.type !== 'localhost';

          // Label for selected value (with health indicator but without version)
          const labelContent = (
            <LabelContent>
              {isChecking ? (
                <LoadingOutlined style={{ fontSize: 10, color: 'var(--color-warning)' }} />
              ) : (
                <HealthIndicator $isHealthy={isHealthy}>
                  ●
                </HealthIndicator>
              )}
              <span>
                {endpoint.icon && <EmojiIcon>{endpoint.icon}</EmojiIcon>}
                {endpoint.name}
              </span>
            </LabelContent>
          );

          return (
            <Option
              key={endpoint.id}
              value={endpoint.id}
              data-testid={`endpoint-option-${endpoint.id}`}
              disabled={isDisabled}
              label={labelContent}
            >
              <OptionWrapper>
                <OptionLeft>
                  {/* Health indicator */}
                  {isChecking ? (
                    <LoadingOutlined style={{ fontSize: 10, color: 'var(--color-warning)' }} />
                  ) : (
                    <HealthIndicator $isHealthy={isHealthy} $isChecking={isChecking}>
                      ●
                    </HealthIndicator>
                  )}

                  <EndpointName $disabled={isDisabled}>
                    {endpoint.icon && <EmojiIcon>{endpoint.icon}</EmojiIcon>}
                    <EndpointNameText>{endpoint.name}</EndpointNameText>
                  </EndpointName>
                </OptionLeft>

                <OptionRight>
                  {/* Version display */}
                  {health?.version && (
                    <VersionLabel>
                      v{health.version}
                    </VersionLabel>
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
                </OptionRight>
              </OptionWrapper>
            </Option>
          );
        })}

        {/* Add custom endpoint option */}
        <Option key="__add_custom__" value="__add_custom__" data-testid="endpoint-option-add-custom">
          <AddCustomOption>
            <PlusOutlined /> Add Custom Endpoint...
          </AddCustomOption>
        </Option>
      </StyledSelect>

      {/* Display selected endpoint URL */}
      {selectedEndpoint && (
        <EndpointUrlText>
          {selectedEndpoint.url}
          {isCheckingHealth && (
            <span style={{ marginLeft: 8 }}>
              <LoadingOutlined style={{ fontSize: DESIGN_TOKENS.FONT_SIZE.XS }} />
            </span>
          )}
        </EndpointUrlText>
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
      {contextHolder}
    </>
  );
};

export default EndpointSelector;
