import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Flex, Form, Input, Modal, Select, Typography } from 'antd';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import apiClient from '@/api/client';
import { useConfirmDialog } from '@/hooks/useConfirmDialog';
import { useDialogState } from '@/hooks/useDialogState';
import { apiConnectionService } from '@/services/apiConnectionService';
import { Endpoint, endpointService } from '@/services/endpointService';
import { showMessage } from '@/utils/messages';
import { ApiOutlined, DeleteOutlined, LoadingOutlined, PlusOutlined } from '@/utils/optimizedIcons';

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
  const { t } = useTranslation('auth');
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
        if (selected) {
          // Endpoint already selected, no action needed
        } else if (endpointService.isLocalhost()) {
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
        } else {
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
      title: t('endpointSelector.removeTitle'),
      content: t('endpointSelector.removeConfirm'),
      onOk: async () => {
        endpointService.removeCustomEndpoint(endpointId);

        // Refresh endpoints list
        const allEndpoints = await endpointService.fetchEndpoints(true);
        setEndpoints(allEndpoints);

        // If removed endpoint was selected, clear selection
        if (selectedEndpoint?.id === endpointId) {
          setSelectedEndpoint(null);
        }

        showMessage('success', t('endpointSelector.removeSuccess'));
      },
    });
  };

  // Show loading state
  if (loading) {
    return (
      <Typography.Text style={{ fontSize: 12 }} type="secondary">
        {t('endpointSelector.loading')}
      </Typography.Text>
    );
  }

  // If no endpoint selected and we have endpoints, show the first one
  const displayValue = selectedEndpoint?.id || endpoints[0]?.id;

  return (
    <>
      <div style={{ display: 'inline-block', width: '100%' }}>
        <Select
          value={displayValue}
          onChange={handleEndpointChange}
          // onDropdownVisibleChange={(open) => {
          // if (open && endpoints.length > 0) {
          // // Check health when dropdown opens
          // checkAllEndpointsHealth(endpoints);
          // }
          // }}
          suffixIcon={<ApiOutlined style={{ fontSize: 18, alignSelf: 'flex-end' }} />}
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
              <Flex align="center" gap={8}>
                {isChecking ? (
                  <LoadingOutlined style={{ fontSize: 12, color: 'var(--ant-color-warning)' }} />
                ) : (
                  <span
                    style={{
                      fontSize: 12,
                      color: isHealthy ? 'var(--ant-color-success)' : 'var(--ant-color-error)',
                    }}
                  >
                    {HEALTH_INDICATOR_SYMBOL}
                  </span>
                )}
                <span>
                  {endpoint.icon && (
                    <span
                      style={{
                        fontSize: 16,
                        lineHeight: 1,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontFamily:
                          "'Apple Color Emoji','Segoe UI Emoji','Segoe UI Symbol','Noto Color Emoji',sans-serif",
                      }}
                    >
                      {endpoint.icon}
                    </span>
                  )}
                  {endpoint.name}
                </span>
              </Flex>
            );

            return (
              <Select.Option
                key={endpoint.id}
                value={endpoint.id}
                data-testid={`endpoint-option-${endpoint.id}`}
                disabled={isDisabled}
                label={labelContent}
              >
                <Flex justify="space-between">
                  <Flex align="center" gap={8}>
                    {/* Health indicator */}
                    {isChecking ? (
                      <LoadingOutlined
                        style={{ fontSize: 12, color: 'var(--ant-color-warning)' }}
                      />
                    ) : (
                      <span
                        style={{
                          fontSize: 12,
                          color: isChecking
                            ? 'var(--ant-color-warning)'
                            : isHealthy
                              ? 'var(--ant-color-success)'
                              : 'var(--ant-color-error)',
                        }}
                      >
                        {HEALTH_INDICATOR_SYMBOL}
                      </span>
                    )}

                    <span style={{ display: 'flex', opacity: isDisabled ? 0.5 : 1 }}>
                      {endpoint.icon && (
                        <span
                          style={{
                            fontSize: 16,
                            lineHeight: 1,
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontFamily:
                              "'Apple Color Emoji','Segoe UI Emoji','Segoe UI Symbol','Noto Color Emoji',sans-serif",
                          }}
                        >
                          {endpoint.icon}
                        </span>
                      )}
                      <p
                        style={{
                          fontSize: 12,
                          maxWidth: 120,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {endpoint.name}
                      </p>
                    </span>
                  </Flex>

                  <Flex align="center" gap={8}>
                    {/* Version display */}
                    {health?.version && (
                      <span style={{ fontSize: 12, color: 'var(--ant-color-text-tertiary)' }}>
                        v{health.version}
                      </span>
                    )}

                    {/* Delete button for custom endpoints */}
                    {endpoint.type === 'custom' && (
                      <DeleteOutlined
                        style={{ fontSize: 12, cursor: 'pointer' }}
                        onClick={(e) => handleRemoveCustomEndpoint(endpoint.id, e)}
                      />
                    )}
                  </Flex>
                </Flex>
              </Select.Option>
            );
          })}

          {/* Add custom endpoint option */}
          <Select.Option
            key="__add_custom__"
            value="__add_custom__"
            data-testid="endpoint-option-add-custom"
          >
            <span style={{ fontSize: 12 }}>
              <PlusOutlined /> {t('endpointSelector.addCustom')}
            </span>
          </Select.Option>
        </Select>

        {/* Display selected endpoint URL */}
        {selectedEndpoint && (
          <Typography.Text
            style={{
              fontSize: 12,
              color: 'var(--ant-color-text-tertiary)',
              textAlign: 'center',
              display: 'block',
            }}
          >
            {selectedEndpoint.url}
            {isCheckingHealth && (
              <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                <LoadingOutlined style={{ fontSize: 12, color: 'var(--ant-color-warning)' }} />
              </span>
            )}
          </Typography.Text>
        )}
      </div>

      {/* Add Custom Endpoint Modal */}
      <Modal
        title={t('endpointSelector.addTitle')}
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
            label={t('endpointSelector.nameLabel')}
            rules={[
              { required: true, message: t('endpointSelector.nameRequired') },
              { min: 2, message: t('endpointSelector.nameMinLength') },
            ]}
          >
            <Input
              placeholder={t('endpointSelector.namePlaceholder')}
              data-testid="custom-endpoint-name-input"
            />
          </Form.Item>

          <Form.Item
            name="url"
            label={t('endpointSelector.urlLabel')}
            rules={[
              { required: true, message: t('endpointSelector.urlRequired') },
              {
                pattern: /^https?:\/\/.+/,
                message: t('endpointSelector.urlFormat'),
              },
            ]}
            extra={t('endpointSelector.urlHelp')}
          >
            <Input
              placeholder={t('endpointSelector.urlPlaceholder')}
              data-testid="custom-endpoint-url-input"
            />
          </Form.Item>

          <Form.Item>
            <Flex justify="flex-end" gap={8} style={{ width: '100%' }}>
              <Button
                onClick={() => {
                  customModal.close();
                  customForm.resetFields();
                }}
              >
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" data-testid="custom-endpoint-submit-button">
                Add Endpoint
              </Button>
            </Flex>
          </Form.Item>
        </Form>
      </Modal>
      {contextHolder}
    </>
  );
};

export default EndpointSelector;
