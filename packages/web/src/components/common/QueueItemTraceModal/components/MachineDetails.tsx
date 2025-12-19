import React from 'react';
import { Card, Col, Collapse, Descriptions, Row, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { RediaccStack, RediaccTag, RediaccText } from '@/components/ui';
import { CodeOutlined, RightOutlined, RetweetOutlined, TeamOutlined, UserOutlined } from '@/utils/optimizedIcons';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { ConsoleOutput } from './ConsoleOutput';
import { StatsPanel } from './StatsPanel';
import { getPriorityInfo } from '../utils';

interface MachineDetailsProps {
  queueDetails: GetTeamQueueItems_ResultSet1;
  totalDurationSeconds: number;
  processingDurationSeconds: number;
  isTaskStale: boolean;
  isDetailedConsoleExpanded: boolean;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
  accumulatedOutput: string;
  theme: 'light' | 'dark';
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  hasContent: boolean;
}

export const MachineDetails: React.FC<MachineDetailsProps> = ({
  queueDetails,
  totalDurationSeconds,
  processingDurationSeconds,
  isTaskStale,
  isDetailedConsoleExpanded,
  setIsDetailedConsoleExpanded,
  accumulatedOutput,
  theme,
  consoleOutputRef,
  hasContent,
}) => {
  const { t } = useTranslation(['queue', 'common']);

  return (
    <Row gutter={[24, 16]}>
      {/* Left Column - Task Details */}
      <Col xs={24} lg={12}>
        <RediaccStack variant="column" fullWidth gap="md">
          <Card size="small" title={t('trace.taskInfo')} data-testid="queue-trace-task-info">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Task ID">
                <RediaccText code>
                  {queueDetails.taskId}
                </RediaccText>
              </Descriptions.Item>
              <Descriptions.Item label="Created By">
                <Space>
                  <UserOutlined />
                  <RediaccText>
                    {queueDetails.createdBy || 'System'}
                  </RediaccText>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Retry Status">
                <Space>
                  <RetweetOutlined />
                  <RediaccTag
                    variant={
                      (queueDetails.retryCount ?? 0) === 0
                        ? 'success'
                        : (queueDetails.retryCount ?? 0) < 2
                          ? 'warning'
                          : 'error'
                    }
                  >
                    {queueDetails.retryCount ?? 0} / 2 retries
                  </RediaccTag>
                  {queueDetails.permanentlyFailed && (
                    <RediaccTag variant="error">Permanently Failed</RediaccTag>
                  )}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Priority">
                <Space>
                  {
                    getPriorityInfo(queueDetails.priority ?? undefined).icon
                  }
                  <RediaccTag
                    variant={
                      getPriorityInfo(queueDetails.priority ?? undefined).color as 'neutral'
                    }
                  >
                    {
                      getPriorityInfo(queueDetails.priority ?? undefined).label
                    }
                  </RediaccTag>
                </Space>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card
            size="small"
            title={t('trace.processingInfo')}
            data-testid="queue-trace-processing-info"
          >
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Machine">
                <Space>
                  <TeamOutlined />
                  <RediaccText>{queueDetails.machineName}</RediaccText>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Team">
                <RediaccText>{queueDetails.teamName}</RediaccText>
              </Descriptions.Item>
              <Descriptions.Item label="Bridge">
                <RediaccText>{queueDetails.bridgeName}</RediaccText>
              </Descriptions.Item>
              <Descriptions.Item label="Region">
                <RediaccText>{queueDetails.regionName}</RediaccText>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <StatsPanel
            queueDetails={queueDetails}
            totalDurationSeconds={totalDurationSeconds}
            processingDurationSeconds={processingDurationSeconds}
            isTaskStale={isTaskStale}
          />
        </RediaccStack>
      </Col>

      {/* Right Column - Response Console */}
      <Col xs={24} lg={12}>
        <Collapse
          data-testid="queue-trace-detailed-console-collapse"
          activeKey={isDetailedConsoleExpanded ? ['console'] : []}
          onChange={(keys) => setIsDetailedConsoleExpanded(keys.includes('console'))}
          expandIcon={({ isActive }) => <RightOutlined rotate={isActive ? 90 : 0} />}
          items={[
            {
              key: 'console',
              label: (
                <Space>
                  <CodeOutlined />
                  <RediaccText>Response (Console)</RediaccText>
                  {queueDetails?.status === 'PROCESSING' && (
                    <RediaccTag icon={<CodeOutlined />} variant="primary">
                      Live Output
                    </RediaccTag>
                  )}
                </Space>
              ),
              children: (
                <ConsoleOutput
                  content={accumulatedOutput
                    .replace(/\\r\\n/g, '\n')
                    .replace(/\\n/g, '\n')
                    .replace(/\\r/g, '\r')}
                  theme={theme}
                  consoleOutputRef={consoleOutputRef}
                  isEmpty={!hasContent}
                />
              ),
            },
          ]}
        />
      </Col>
    </Row>
  );
};
