import React from 'react';
import { Card, Col, Collapse, Descriptions, Flex, Row, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  CodeOutlined,
  RightOutlined,
  RetweetOutlined,
  TeamOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { ConsoleOutput } from './ConsoleOutput';
import { StatsPanel } from './StatsPanel';
import { getPriorityInfo } from '../utils';

interface MachineDetailsProps {
  queueDetails: GetTeamQueueItems_ResultSet1;
  totalDurationSeconds: number;
  processingDurationSeconds: number;
  isDetailedConsoleExpanded: boolean;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
  accumulatedOutput: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  hasContent: boolean;
}

export const MachineDetails: React.FC<MachineDetailsProps> = ({
  queueDetails,
  totalDurationSeconds,
  processingDurationSeconds,
  isDetailedConsoleExpanded,
  setIsDetailedConsoleExpanded,
  accumulatedOutput,
  consoleOutputRef,
  hasContent,
}) => {
  const { t } = useTranslation(['queue', 'common']);

  return (
    <Row gutter={[24, 16]}>
      {/* Left Column - Task Details */}
      <Col xs={24} lg={12}>
        <Flex vertical gap={16} className="w-full">
          <Card size="small" title={t('trace.taskInfo')} data-testid="queue-trace-task-info">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Task ID">
                <Typography.Text code>{queueDetails.taskId}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Created By">
                <Space>
                  <UserOutlined />
                  <Typography.Text>{queueDetails.createdBy || 'System'}</Typography.Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Retry Status">
                <Space>
                  <RetweetOutlined />
                  <Tag>{queueDetails.retryCount ?? 0} / 2 retries</Tag>
                  {queueDetails.permanentlyFailed && <Tag>Permanently Failed</Tag>}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Priority">
                <Space>
                  {getPriorityInfo(queueDetails.priority ?? undefined).icon}
                  <Tag>{getPriorityInfo(queueDetails.priority ?? undefined).label}</Tag>
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
                  <Typography.Text>{queueDetails.machineName}</Typography.Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Team">
                <Typography.Text>{queueDetails.teamName}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Bridge">
                <Typography.Text>{queueDetails.bridgeName}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Region">
                <Typography.Text>{queueDetails.regionName}</Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <StatsPanel
            queueDetails={queueDetails}
            totalDurationSeconds={totalDurationSeconds}
            processingDurationSeconds={processingDurationSeconds}
          />
        </Flex>
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
                  <Typography.Text>Response (Console)</Typography.Text>
                  {queueDetails?.status === 'PROCESSING' && (
                    <Tag icon={<CodeOutlined />}>Live Output</Tag>
                  )}
                </Space>
              ),
              children: (
                <ConsoleOutput
                  content={accumulatedOutput
                    .replace(/\\r\\n/g, '\n')
                    .replace(/\\n/g, '\n')
                    .replace(/\\r/g, '\r')}
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
