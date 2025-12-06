import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Modal, Form, Input, Select } from 'antd';
import styled from 'styled-components';
import { PlusOutlined } from '@/utils/optimizedIcons';
import { endpointService, Endpoint } from '@/services/endpointService';
import { apiConnectionService } from '@/services/apiConnectionService';
import { showMessage } from '@/utils/messages';
import apiClient from '@/api/client';
import axios from 'axios';
import { useDialogState } from '@/hooks/useDialogState';
import { useConfirmDialog } from '@/hooks/useConfirmDialog';
import { RediaccButton as Button } from '@/components/ui';
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
  EndpointNameText,
  CheckingSpinner,
  SelectorWrapper,
  EndpointSuffixIcon,
  DeleteEndpointIcon,
  SpinnerWrapper,
  FormActions,
} from './styles';

const { Option } = Select;

const FormActionsRow = styled(Form.Item)`
 margin-bottom: 0;
`;

interface EndpointHealth {
  isHealthy: boolean;
  version?: string;
  lastChecked: number;
  checking?: boolean;
}

interface EndpointSelectorProps {
  onHealthCheckComplete?: (hasHealthyEndpoint: boolean) => void;
}

const HEALTH_INDICATOR_SYMBOL = '●';

const EndpointSelector: React.FC<EndpointSelectorProps> = ({ onHealthCheckComplete }) => {
  const { confirm, contextHolder } = useConfirmDialog();
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>(null);
  const [loading, setLoading] = useState(true);
  const customModal = useDialogState<void>();
  const [customForm] = Form.useForm();
  const [healthStatus, setHealthStatus] = useState<Record<string, EndpointHealth>>({});
  const healthStatusRef = useRef(healthStatus);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  const HEALTH_CACHE_DURATION = 10000; // 10 seconds
  const HEALTH_CHECK_TIMEOUT = 2500; // 2.5 seconds

  /**
   * Check health for a single endpoint
   */
  const checkEndpointHealth = async (endpoint: Endpoint): Promise<EndpointHealth> => {
    try {
      const response = await axios.get(`${endpoint.url}/health`, {
        timeout: HEALTH_CHECK_TIMEOUT,
        validateStatus: (status) => status < 500,
      });

      return {
        isHealthy: response.data?.status === 'healthy',
        version: response.data?.version,
        lastChecked: Date.now(),
      };
    } catch (error) {
      console.warn(`Health check failed for ${endpoint.name}:`, error);
      return {
        isHealthy: false,
        lastChecked: Date.now(),
      };
    }
  };

  useEffect(() => {
    healthStatusRef.current = healthStatus;
  }, [healthStatus]);

  /**
   * Check health for all endpoints
   */
  const checkAllEndpointsHealth = useCallback(
    async (endpointsList: Endpoint[]): Promise<Record<string, EndpointHealth>> => {
      setIsCheckingHealth(true);
      const healthChecks: Record<string, EndpointHealth> = {};

      // Check health for each endpoint in parallel
      const promises = endpointsList.map(async (endpoint) => {
        // Check if cached health is still valid
        const cached = healthStatusRef.current[endpoint.id];
        if (cached && Date.now() - cached.lastChecked < HEALTH_CACHE_DURATION) {
          healthChecks[endpoint.id] = cached;
          return;
        }

        // Set checking state
        healthChecks[endpoint.id] = {
          isHealthy: false,
          checking: true,
          lastChecked: Date.now(),
        };

        // Perform health check
        const health = await checkEndpointHealth(endpoint);
        healthChecks[endpoint.id] = health;
      });

      await Promise.all(promises);
      setHealthStatus(healthChecks);
      setIsCheckingHealth(false);

      return healthChecks;
    },
    []
  );

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
          const existingEndpoint = allEndpoints.find((e) => e.url === dynamicApiUrl);

          if (!existingEndpoint) {
            // Add dynamic endpoint
            const dynamicEndpoint: Endpoint = {
              id: 'dynamic-current-domain',
              name: 'Current Domain',
              url: dynamicApiUrl,
              type: 'dynamic',
              description: `API at ${currentDomain}`,
              icon: '🌍',
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
          // Find all localhost endpoints and select the first healthy one
          const localhostEndpoints = allEndpoints.filter((e) => e.type === 'localhost');
          const healthyLocalhostEndpoint = localhostEndpoints.find(
            (e) => healthChecks[e.id]?.isHealthy
          );

          if (healthyLocalhostEndpoint) {
            selected = healthyLocalhostEndpoint;
            endpointService.setSelectedEndpoint(healthyLocalhostEndpoint);
            console.warn(
              `[EndpointSelector] Auto-selected healthy localhost endpoint: ${healthyLocalhostEndpoint.url}`
            );
          } else if (localhostEndpoints.length > 0) {
            // Fallback to first localhost if none are healthy (user can still try)
            selected = localhostEndpoints[0];
            endpointService.setSelectedEndpoint(localhostEndpoints[0]);
            console.warn(
              `[EndpointSelector] No healthy localhost found, using first: ${localhostEndpoints[0].url}`
            );
          }
        } else if (!selected) {
          // For non-localhost domains, if no saved selection exists, check and auto-select dynamic endpoint
          const dynamicEndpoint = allEndpoints.find((e) => e.type === 'dynamic');
          if (dynamicEndpoint) {
            // Check if dynamic endpoint is healthy
            const health = await checkEndpointHealth(dynamicEndpoint);
            if (health.isHealthy) {
              selected = dynamicEndpoint;
              endpointService.setSelectedEndpoint(dynamicEndpoint);
              console.warn(
                `[EndpointSelector] Auto-selected healthy dynamic endpoint: ${dynamicEndpoint.url}`
              );
            } else {
              console.warn(
                `[EndpointSelector] Dynamic endpoint is not healthy, skipping auto-selection`
              );
            }
          }
        }

        // If no selection (not localhost), get from connection service
        if (!selected) {
          const connectionInfo = apiConnectionService.getSelectedEndpoint();
          if (connectionInfo) {
            selected = allEndpoints.find((e) => e.url === connectionInfo.url) || null;
          }
        }

        setSelectedEndpoint(selected);

        // If we have a selected endpoint, update the API client immediately
        if (selected) {
          apiClient.updateApiUrl(selected.url);
          console.warn(`[EndpointSelector] Applied endpoint: ${selected.name} (${selected.url})`);
        }

        // Notify parent about health check completion
        if (onHealthCheckComplete) {
          const hasHealthyEndpoint = Object.values(healthChecks).some((h) => h.isHealthy);
          onHealthCheckComplete(hasHealthyEndpoint);
        }
      } catch (error) {
        console.warn('Failed to fetch endpoints', error);
      } finally {
        setLoading(false);
      }
    };

    fetchEndpointsAndSelection();
  }, [onHealthCheckComplete, checkAllEndpointsHealth]);

  const handleEndpointChange = async (value: unknown) => {
    if (typeof value !== 'string') {
      return;
    }
    const endpointValue = value;
    if (endpointValue === '__add_custom__') {
      customModal.open();
      return;
    }

    const endpoint = endpoints.find((e) => e.id === endpointValue);
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
      customModal.close();
      customForm.resetFields();
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to add custom endpoint';
      showMessage('error', errorMessage);
    }
  };

  const handleRemoveCustomEndpoint = (endpointId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent dropdown from closing

    confirm({
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
      },
    });
  };

  // Show loading state
  if (loading) {
    return <LoadingText color="secondary">Loading...</LoadingText>;
  }

  // If no endpoint selected and we have endpoints, show the first one
  const displayValue = selectedEndpoint?.id || endpoints[0]?.id;

  return (
    <>
      <SelectorWrapper>
        <StyledSelect
          value={displayValue}
          onChange={handleEndpointChange}
          // onDropdownVisibleChange={(open) => {
          // if (open && endpoints.length > 0) {
          // // Check health when dropdown opens
          // checkAllEndpointsHealth(endpoints);
          // }
          // }}
          size="sm"
          suffixIcon={<EndpointSuffixIcon />}
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
            const isDisabled =
              (!health || (!health.isHealthy && !health.checking)) && endpoint.type !== 'localhost';

            // Label for selected value (with health indicator but without version)
            const labelContent = (
              <LabelContent>
                {isChecking ? (
                  <CheckingSpinner />
                ) : (
                  <HealthIndicator $isHealthy={isHealthy}>
                    {HEALTH_INDICATOR_SYMBOL}
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
                      <CheckingSpinner />
                    ) : (
                      <HealthIndicator $isHealthy={isHealthy} $isChecking={isChecking}>
                        {HEALTH_INDICATOR_SYMBOL}
                      </HealthIndicator>
                    )}

                    <EndpointName $disabled={isDisabled}>
                      {endpoint.icon && <EmojiIcon>{endpoint.icon}</EmojiIcon>}
                      <EndpointNameText>{endpoint.name}</EndpointNameText>
                    </EndpointName>
                  </OptionLeft>

                  <OptionRight>
                    {/* Version display */}
                    {health?.version && <VersionLabel>v{health.version}</VersionLabel>}

                    {/* Delete button for custom endpoints */}
                    {endpoint.type === 'custom' && (
                      <DeleteEndpointIcon
                        onClick={(e) => handleRemoveCustomEndpoint(endpoint.id, e)}
                      />
                    )}
                  </OptionRight>
                </OptionWrapper>
              </Option>
            );
          })}

          {/* Add custom endpoint option */}
          <Option
            key="__add_custom__"
            value="__add_custom__"
            data-testid="endpoint-option-add-custom"
          >
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
              <SpinnerWrapper>
                <CheckingSpinner />
              </SpinnerWrapper>
            )}
          </EndpointUrlText>
        )}
      </SelectorWrapper>

      {/* Add Custom Endpoint Modal */}
      <Modal
        title="Add Custom Endpoint"
        open={customModal.isOpen}
        onCancel={() => {
          customModal.close();
          customForm.resetFields();
        }}
        footer={null}
      >
        <Form form={customForm} layout="vertical" onFinish={handleAddCustomEndpoint}>
          <Form.Item
            name="name"
            label="Endpoint Name"
            rules={[
              { required: true, message: 'Please enter a name for this endpoint' },
              { min: 2, message: 'Name must be at least 2 characters' },
            ]}
          >
            <Input placeholder="e.g., Staging Server" data-testid="custom-endpoint-name-input" />
          </Form.Item>

          <Form.Item
            name="url"
            label="API URL"
            rules={[
              { required: true, message: 'Please enter the API URL' },
              {
                pattern: /^https?:\/\/.+/,
                message: 'URL must start with http:// or https://',
              },
            ]}
            extra="The URL will be normalized to end with /api if not already"
          >
            <Input placeholder="https://api.example.com" data-testid="custom-endpoint-url-input" />
          </Form.Item>

          <FormActionsRow>
            <FormActions>
              <Button
                onClick={() => {
                  customModal.close();
                  customForm.resetFields();
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                htmlType="submit"
                data-testid="custom-endpoint-submit-button"
              >
                Add Endpoint
              </Button>
            </FormActions>
          </FormActionsRow>
        </Form>
      </Modal>
      {contextHolder}
    </>
  );
};

export default EndpointSelector;
