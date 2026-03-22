import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import {
  Card,
  Col,
  Collapse,
  Descriptions,
  Flex,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
} from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  CodeOutlined,
  RetweetOutlined,
  RightOutlined,
  TeamOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { ConsoleViewMode } from '../types';
import { getPriorityInfo } from '../utils';
import { ConsoleOutput } from './ConsoleOutput';
import { StatsPanel } from './StatsPanel';

interface MachineDetailsProps {
  queueDetails: GetTeamQueueItems_ResultSet1;
  totalDurationSeconds: number;
  processingDurationSeconds: number;
  isDetailedConsoleExpanded: boolean;
  setIsDetailedConsoleExpanded: (expanded: boolean) => void;
  accumulatedOutput: string;
  consoleOutputRef: React.RefObject<HTMLDivElement | null>;
  hasContent: boolean;
  consoleViewMode: ConsoleViewMode;
  setConsoleViewMode: (mode: ConsoleViewMode) => void;
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
  consoleViewMode,
  setConsoleViewMode,
}) => {
  const { t } = useTranslation(['queue', 'common']);

  return (
    <Row gutter={[24, 16]}>
      {/* Left Column - Task Details */}
      <Col xs={24} lg={12}>
        <Flex vertical className="w-full">
          <Card size="small" title={t('trace.taskInfo')} data-testid="queue-trace-task-info">
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('trace.taskId')}>
                <Typography.Text code>{queueDetails.taskId}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('trace.createdBy')}>
                <Space>
                  <UserOutlined />
                  <Typography.Text>{queueDetails.createdBy ?? t('trace.system')}</Typography.Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('trace.retryStatus')}>
                <Space>
                  <RetweetOutlined />
                  <Tag>
                    {t('trace.retriesFormat', { current: queueDetails.retryCount ?? 0, max: 2 })}
                  </Tag>
                  {queueDetails.permanentlyFailed && <Tag>{t('trace.permanentlyFailed')}</Tag>}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('trace.priority')}>
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
              <Descriptions.Item label={t('trace.machine')}>
                <Space>
                  <TeamOutlined />
                  <Typography.Text>{queueDetails.machineName}</Typography.Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('trace.team')}>
                <Typography.Text>{queueDetails.teamName}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('trace.bridge')}>
                <Typography.Text>{queueDetails.bridgeName}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('trace.region')}>
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
                  <Typography.Text>{t('trace.responseConsole')}</Typography.Text>
                  {queueDetails.status === 'PROCESSING' && (
                    <Tag icon={<CodeOutlined />}>{t('trace.liveOutput')}</Tag>
                  )}
                </Space>
              ),
              extra: (
                <Segmented
                  size="small"
                  value={consoleViewMode}
                  onChange={(value) => setConsoleViewMode(value as ConsoleViewMode)}
                  options={[
                    { label: t('trace.structuredLog.viewStructured'), value: 'structured' },
                    { label: t('trace.structuredLog.viewRaw'), value: 'raw' },
                  ]}
                  onClick={(e) => e.stopPropagation()}
                  data-testid="console-output-view-toggle-detailed"
                />
              ),
              children: (
                <ConsoleOutput
                  content={accumulatedOutput}
                  consoleOutputRef={consoleOutputRef}
                  isEmpty={!hasContent}
                  viewMode={consoleViewMode}
                />
              ),
            },
          ]}
        />
      </Col>
    </Row>
  );
};
