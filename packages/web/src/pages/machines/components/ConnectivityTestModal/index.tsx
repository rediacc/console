import React, { useEffect, useState } from 'react';
import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { createStatusColumn, createTruncatedColumn } from '@/components/common/columns';
import { InlineStack, StatusIcon } from '@/components/common/styled';
import { RediaccAlert, RediaccButton, RediaccStack, RediaccText } from '@/components/ui';
import type { QueueItemCompletionResult } from '@/services/helloService';
import { usePingFunction } from '@/services/pingService';
import { ModalContentStack, ModalFooterActions } from '@/styles/primitives';
import type { Machine } from '@/types';
import { ModalSize } from '@/types/modal';
import { showMessage } from '@/utils/messages';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  WifiOutlined,
} from '@/utils/optimizedIcons';
import {
  MessageText,
  ModalContent,
  ProgressBar,
  ProgressSection,
  ResourceTag,
  StyledModal,
  StyledTable,
  SummaryContainer,
  SummaryMetric,
  SummaryMetrics,
  SummaryValue,
} from './styles';
import type { ColumnsType } from 'antd/es/table/interface';

interface ConnectivityTestModalProps {
  open: boolean;
  onClose: () => void;
  machines: Machine[];
  teamFilter?: string | string[];
}

interface TestResult {
  machineName: string;
  teamName: string;
  bridgeName: string;
  status: 'pending' | 'testing' | 'success' | 'failed';
  message?: string;
  taskId?: string;
  duration?: number;
  timestamp?: string;
}

const ConnectivityTestModal: React.FC<ConnectivityTestModalProps> = ({
  open,
  onClose,
  machines,
}) => {
  const { t } = useTranslation(['machines', 'common']);
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentMachineIndex, setCurrentMachineIndex] = useState(-1);

  const { executePingForMachine, waitForQueueItemCompletion } = usePingFunction();

  // Initialize test results when modal opens
  useEffect(() => {
    if (open && machines.length > 0) {
      const initialResults: TestResult[] = machines.map((machine) => ({
        machineName: machine.machineName,
        teamName: machine.teamName,
        bridgeName: machine.bridgeName,
        status: 'pending',
      }));
      setTestResults(initialResults);
      setProgress(0);
      setCurrentMachineIndex(-1);
    }
  }, [open, machines]);

  // Helper to format completion message
  const formatCompletionMessage = (result: QueueItemCompletionResult) => {
    if (result.success) {
      return t('machines:connectionSuccessful');
    }
    if (result.status === 'TIMEOUT') {
      return t('machines:testTimeout');
    }
    return result.message || t('machines:connectionFailed');
  };

  // Run connectivity test for a single machine
  const testMachineConnectivity = async (machine: Machine, index: number): Promise<void> => {
    const startTime = Date.now();

    // Update status to testing
    setTestResults((prev) =>
      prev.map((result, i) =>
        i === index ? { ...result, status: 'testing', timestamp: new Date().toISOString() } : result
      )
    );

    try {
      // Execute ping function using the shared service
      // The ping service will automatically fetch the team vault data
      const result = await executePingForMachine(machine, {
        priority: 4, // Normal priority for connectivity tests
        description: 'Connectivity test',
        addedVia: 'connectivity-test',
      });

      if (result.success && result.taskId) {
        // Update with taskId
        setTestResults((prev) =>
          prev.map((r, i) => (i === index ? { ...r, taskId: result.taskId } : r))
        );

        // Wait for completion
        const completionResult = await waitForQueueItemCompletion(result.taskId);
        const duration = Date.now() - startTime;

        // Update final status
        setTestResults((prev) =>
          prev.map((r, i) =>
            i === index
              ? {
                  ...r,
                  status: completionResult.success ? 'success' : 'failed',
                  message: formatCompletionMessage(completionResult),
                  duration,
                }
              : r
          )
        );
      } else {
        throw new Error(result.error || 'Failed to create test task');
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create test task';
      const duration = Date.now() - startTime;
      setTestResults((prev) =>
        prev.map((result, i) =>
          i === index
            ? {
                ...result,
                status: 'failed',
                message: errorMessage,
                duration,
              }
            : result
        )
      );
    }
  };

  // Run all tests sequentially
  const runAllTests = async () => {
    setIsRunning(true);

    for (let i = 0; i < machines.length; i++) {
      setCurrentMachineIndex(i);
      setProgress(Math.round((i / machines.length) * 100));
      await testMachineConnectivity(machines[i], i);
    }

    setProgress(100);
    setIsRunning(false);
    setCurrentMachineIndex(-1);

    // Show summary
    const successCount = testResults.filter((r) => r.status === 'success').length;
    const failedCount = testResults.filter((r) => r.status === 'failed').length;

    if (failedCount === 0) {
      showMessage('success', t('machines:allMachinesConnected', { count: successCount }));
    } else {
      showMessage(
        'warning',
        t('machines:machinesConnectedWithFailures', { successCount, failedCount })
      );
    }
  };

  // Table columns
  const teamColumn = createTruncatedColumn<TestResult>({
    title: t('machines:team'),
    dataIndex: 'teamName',
    key: 'teamName',
    renderWrapper: (content) => <ResourceTag>{content}</ResourceTag>,
  });

  const bridgeColumn = createTruncatedColumn<TestResult>({
    title: t('machines:bridge'),
    dataIndex: 'bridgeName',
    key: 'bridgeName',
    renderWrapper: (content) => <ResourceTag>{content}</ResourceTag>,
  });

  const statusColumn = createStatusColumn<TestResult>({
    title: t('machines:status'),
    dataIndex: 'status',
    key: 'status',
    width: 140,
    statusMap: {
      pending: { color: 'default', label: t('machines:pending'), icon: <ClockCircleOutlined /> },
      testing: { color: 'blue', label: t('machines:testing'), icon: <SyncOutlined spin /> },
      success: { color: 'success', label: t('machines:connected'), icon: <CheckCircleOutlined /> },
      failed: { color: 'error', label: t('machines:failed'), icon: <CloseCircleOutlined /> },
    },
  });

  const baseMessageColumn = createTruncatedColumn<TestResult>({
    title: t('machines:message'),
    dataIndex: 'message',
    key: 'message',
    ellipsis: true,
    renderText: (message) => message || '-',
  });

  const columns: ColumnsType<TestResult> = [
    {
      title: t('machines:machineName'),
      dataIndex: 'machineName',
      key: 'machineName',
      render: (name: string, record: TestResult) => {
        const renderIcon = () => {
          switch (record.status) {
            case 'testing':
              return <SyncOutlined spin data-testid={`connectivity-status-icon-testing-${name}`} />;
            case 'success':
              return (
                <CheckCircleOutlined data-testid={`connectivity-status-icon-success-${name}`} />
              );
            case 'failed':
              return (
                <CloseCircleOutlined data-testid={`connectivity-status-icon-failed-${name}`} />
              );
            case 'pending':
            default:
              return (
                <ClockCircleOutlined data-testid={`connectivity-status-icon-pending-${name}`} />
              );
          }
        };

        return (
          <InlineStack data-testid={`connectivity-machine-${name}`}>
            <StatusIcon $variant={record.status}>{renderIcon()}</StatusIcon>
            <RediaccText weight="semibold">{name}</RediaccText>
          </InlineStack>
        );
      },
    },
    teamColumn,
    bridgeColumn,
    {
      ...statusColumn,
      render: (status: TestResult['status'], record, index) => (
        <span data-testid={`connectivity-status-tag-${record.machineName}-${status}`}>
          {statusColumn.render?.(status, record, index) as React.ReactNode}
        </span>
      ),
    },
    {
      title: t('machines:responseTime'),
      dataIndex: 'duration',
      key: 'duration',
      width: 120,
      render: (duration?: number) => {
        if (!duration) return '-';
        if (duration < 1000) return `${duration}ms`;
        return `${(duration / 1000).toFixed(1)}s`;
      },
    },
    {
      ...baseMessageColumn,
      render: (message: string | undefined, record, index) => {
        if (!message) {
          return baseMessageColumn.render?.(message, record, index) as React.ReactNode;
        }
        const truncated = baseMessageColumn.render?.(message, record, index) as React.ReactNode;
        return <MessageText $isError={record.status === 'failed'}>{truncated}</MessageText>;
      },
    },
  ];

  return (
    <StyledModal
      data-testid="connectivity-modal"
      title={
        <RediaccStack direction="horizontal" gap="sm" align="center">
          <WifiOutlined />
          <span>{t('machines:connectivityTest')}</span>
        </RediaccStack>
      }
      open={open}
      onCancel={onClose}
      className={ModalSize.ExtraLarge}
      destroyOnClose
      footer={
        <ModalFooterActions>
          <RediaccButton
            icon={<SyncOutlined />}
            onClick={runAllTests}
            disabled={isRunning || machines.length === 0}
            loading={isRunning}
            data-testid="connectivity-run-test-button"
          >
            {isRunning ? t('machines:testing') : t('machines:runTest')}
          </RediaccButton>
          <Tooltip title="Close">
            <RediaccButton
              iconOnly
              icon={<CloseCircleOutlined />}
              onClick={onClose}
              data-testid="connectivity-close-button"
              aria-label="Close"
            />
          </Tooltip>
        </ModalFooterActions>
      }
    >
      <ModalContent>
        <ModalContentStack>
          {isRunning && (
            <ProgressSection data-testid="connectivity-progress-container">
              <ProgressBar
                percent={progress}
                status="active"
                data-testid="connectivity-progress-bar"
              />
              {currentMachineIndex >= 0 && currentMachineIndex < machines.length && (
                <RediaccText size="xs" color="secondary" data-testid="connectivity-progress-text">
                  {t('machines:testingMachine', {
                    machineName: machines[currentMachineIndex].machineName,
                  })}
                </RediaccText>
              )}
            </ProgressSection>
          )}

          <RediaccAlert
            message={t('machines:connectivityTestDescription')}
            variant="info"
            showIcon
            icon={<WifiOutlined />}
            data-testid="connectivity-info-alert"
            style={{ borderRadius: '12px', fontSize: '14px' }}
          />

          <StyledTable
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            columns={columns as any}
            dataSource={testResults}
            rowKey="machineName"
            pagination={false}
            scroll={{ y: 400 }}
            loading={machines.length === 0}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            rowClassName={(record: any) => `status-${record.status}`}
            data-testid="connectivity-results-table"
          />

          {!isRunning && testResults.some((r) => r.status !== 'pending') && (
            <SummaryContainer data-testid="connectivity-summary-statistics">
              <SummaryMetrics>
                <SummaryMetric data-testid="connectivity-total-machines">
                  <RediaccText color="secondary">{t('machines:totalMachines')}:</RediaccText>
                  <SummaryValue>{machines.length}</SummaryValue>
                </SummaryMetric>
                <SummaryMetric data-testid="connectivity-connected-count">
                  <RediaccText color="secondary">{t('machines:connected')}:</RediaccText>
                  <SummaryValue $variant="success">
                    {testResults.filter((r) => r.status === 'success').length}
                  </SummaryValue>
                </SummaryMetric>
                <SummaryMetric data-testid="connectivity-failed-count">
                  <RediaccText color="secondary">{t('machines:failed')}:</RediaccText>
                  <SummaryValue $variant="error">
                    {testResults.filter((r) => r.status === 'failed').length}
                  </SummaryValue>
                </SummaryMetric>
                <SummaryMetric data-testid="connectivity-average-response">
                  <RediaccText color="secondary">{t('machines:averageResponse')}:</RediaccText>
                  <SummaryValue>
                    {(() => {
                      const successfulTests = testResults.filter(
                        (r) => r.status === 'success' && r.duration
                      );
                      if (successfulTests.length === 0) return '-';
                      const avgDuration =
                        successfulTests.reduce((sum, r) => sum + (r.duration || 0), 0) /
                        successfulTests.length;
                      return avgDuration < 1000
                        ? `${Math.round(avgDuration)}ms`
                        : `${(avgDuration / 1000).toFixed(1)}s`;
                    })()}
                  </SummaryValue>
                </SummaryMetric>
              </SummaryMetrics>
            </SummaryContainer>
          )}
        </ModalContentStack>
      </ModalContent>
    </StyledModal>
  );
};

export default ConnectivityTestModal;
