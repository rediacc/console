import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Flex, Form, Input, Modal, Select, Typography } from 'antd';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import apiClient from '@/api/client';
import { useConfirmDialog } from '@/hooks/useConfirmDialog';
import { useDialogState } from '@/hooks/useDialogState';
import { apiConnectionService } from '@/services/apiConnectionService';
import { Endpoint, endpointService } from '@/services/endpointService';
import { versionService } from '@/services/versionService';
import { showMessage } from '@/utils/messages';
import { ApiOutlined, DeleteOutlined, LoadingOutlined, PlusOutlined } from '@/utils/optimizedIcons';

interface EndpointHealth {
  isHealthy: boolean;
  version?: string;
  lastChecked: number;
  checking?: boolean;
}

const HEALTH_INDICATOR_SYMBOL = '●';

const EndpointSelector: React.FC = () => {
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
  const [versionDisplay, setVersionDisplay] = useState<string>('');

  const HEALTH_CACHE_DURATION = 10000; // 10 seconds
  const HEALTH_CHECK_TIMEOUT = 2500; // 2.5 seconds

  // Fetch version info on mount
  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const versionInfo = await versionService.getVersion();
        const formattedVersion = versionService.formatVersion(versionInfo.version);

        if (formattedVersion === 'Development') {
          setVersionDisplay('Development');
        } else {
          const buildType = import.meta.env.VITE_BUILD_TYPE || 'DEBUG';
          const buildLabel = buildType === 'RELEASE' ? 'Release' : 'Development';
          setVersionDisplay(`${buildLabel} - ${formattedVersion}`);
        }
      } catch (error) {
        console.warn('Failed to fetch version information', error);
        setVersionDisplay('Development');
      }
    };

    fetchVersion();
  }, []);

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
      } catch (error) {
        console.warn('Failed to fetch endpoints', error);
      } finally {
        setLoading(false);
      }
    };

    fetchEndpointsAndSelection();
  }, [checkAllEndpointsHealth]);

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
    return <Typography.Text>{t('endpointSelector.loading')}</Typography.Text>;
  }

  // If no endpoint selected and we have endpoints, show the first one
  const displayValue = selectedEndpoint?.id || endpoints[0]?.id;

  return (
    <>
      <Flex vertical gap={4} align="center">
        {/* Display selected endpoint URL with version */}
        {selectedEndpoint && (
          <Typography.Text>
            {selectedEndpoint.url}
            {versionDisplay && ` - ${versionDisplay}`}
            {isCheckingHealth && (
              <Flex align="center" className="inline-flex">
                <LoadingOutlined />
              </Flex>
            )}
          </Typography.Text>
        )}

        <Select
          value={displayValue}
          onChange={handleEndpointChange}
          suffixIcon={<ApiOutlined />}
          popupMatchSelectWidth={false}
          data-testid="endpoint-selector"
        >
          {/* Predefined and custom endpoints */}
          {endpoints.map((endpoint) => {
            const health = healthStatus[endpoint.id];
            const isChecking = health?.checking;
            // Disable if not checked yet or unhealthy (except localhost which is always enabled)
            const isDisabled =
              (!health || (!health.isHealthy && !health.checking)) && endpoint.type !== 'localhost';

            // Label for selected value (with health indicator)
            const labelContent = (
              <Flex align="center" gap={8}>
                {isChecking ? (
                  <LoadingOutlined />
                ) : (
                  <Typography.Text>{HEALTH_INDICATOR_SYMBOL}</Typography.Text>
                )}
                <Typography.Text>{endpoint.name}</Typography.Text>
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
                <Flex justify="space-between" align="center">
                  <Flex align="center" gap={8}>
                    {/* Health indicator */}
                    {isChecking ? (
                      <LoadingOutlined />
                    ) : (
                      <Typography.Text>{HEALTH_INDICATOR_SYMBOL}</Typography.Text>
                    )}

                    <Typography.Text
                      // eslint-disable-next-line no-restricted-syntax
                      style={{ opacity: isDisabled ? 0.5 : 1 }}
                    >
                      {endpoint.name}
                    </Typography.Text>
                  </Flex>

                  {/* Delete button for custom endpoints */}
                  {endpoint.type === 'custom' && (
                    <DeleteOutlined
                      className="cursor-pointer"
                      onClick={(e) => handleRemoveCustomEndpoint(endpoint.id, e)}
                    />
                  )}
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
            <Typography.Text>
              <PlusOutlined /> {t('endpointSelector.addCustom')}
            </Typography.Text>
          </Select.Option>
        </Select>
      </Flex>

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
            <Flex justify="flex-end" gap={8} className="w-full">
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
