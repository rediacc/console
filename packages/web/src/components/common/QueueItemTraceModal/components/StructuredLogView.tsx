import type { LogLevel, ParsedLogLine } from '@rediacc/shared/utils';
import { Flex, Grid, List, Space, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { MobileCard } from '@/components/common/MobileCard';
import {
  CloseCircleOutlined,
  CodeOutlined,
  InfoCircleOutlined,
  WarningOutlined,
} from '@/utils/optimizedIcons';

interface StructuredLogViewProps {
  /** Parsed log entries */
  entries: ParsedLogLine[];
  /** Reference for scroll container */
  scrollRef?: React.RefObject<HTMLElement | null>;
}

// Level to color/icon mapping
const LEVEL_CONFIG: Record<LogLevel, { color: string; icon: React.ReactNode }> = {
  debug: { color: 'default', icon: <CodeOutlined /> },
  info: { color: 'blue', icon: <InfoCircleOutlined /> },
  warning: { color: 'gold', icon: <WarningOutlined /> },
  error: { color: 'red', icon: <CloseCircleOutlined /> },
};

/**
 * Format ISO timestamp to HH:MM:SS for display
 */
function formatTime(timestamp?: string): string {
  if (!timestamp) return '-';
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return timestamp;
  }
}

/**
 * Render metadata tags for extras (key=value pairs)
 */
function renderExtras(extras?: Record<string, string>): React.ReactNode {
  if (!extras) return null;
  return (
    <Space size={4} wrap className="mt-1">
      {Object.entries(extras).map(([key, value]) => (
        <Tooltip key={key} title={`${key}=${value}`}>
          <Tag className="text-[11px] m-0">
            {key}={value}
          </Tag>
        </Tooltip>
      ))}
    </Space>
  );
}

export const StructuredLogView: React.FC<StructuredLogViewProps> = ({ entries, scrollRef }) => {
  const { t } = useTranslation('queue');
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.sm;

  // Table columns for desktop view
  const columns: ColumnsType<ParsedLogLine> = [
    {
      title: t('trace.structuredLog.time'),
      dataIndex: 'time',
      key: 'time',
      width: 90,
      render: (time: string | undefined) => (
        <Typography.Text type="secondary" className="text-xs whitespace-nowrap">
          {formatTime(time)}
        </Typography.Text>
      ),
    },
    {
      title: t('trace.structuredLog.level'),
      dataIndex: 'level',
      key: 'level',
      width: 90,
      render: (level: LogLevel) => {
        const config = LEVEL_CONFIG[level];
        return (
          <Tag color={config.color} icon={config.icon} className="m-0">
            {level.toUpperCase()}
          </Tag>
        );
      },
    },
    {
      title: t('trace.structuredLog.message'),
      dataIndex: 'message',
      key: 'message',
      render: (message: string, record: ParsedLogLine) => (
        <Flex vertical>
          <Typography.Text className="break-words">{message}</Typography.Text>
          {renderExtras(record.extras)}
        </Flex>
      ),
    },
  ];

  // Mobile view using List with MobileCard
  if (isMobile) {
    return (
      <Flex ref={scrollRef} className="max-h-[300px] overflow-y-auto">
        <List
          dataSource={entries}
          size="small"
          split={false}
          renderItem={(entry) => (
            <List.Item key={entry.index} className="py-1 px-0">
              <MobileCard>
                <Flex vertical className="w-full gap-1">
                  {entry.isStructured ? (
                    <>
                      <Flex justify="space-between" align="center">
                        <Tag
                          color={LEVEL_CONFIG[entry.level].color}
                          icon={LEVEL_CONFIG[entry.level].icon}
                          className="m-0"
                        >
                          {entry.level.toUpperCase()}
                        </Tag>
                        <Typography.Text type="secondary" className="text-[11px]">
                          {formatTime(entry.time)}
                        </Typography.Text>
                      </Flex>
                      <Typography.Text className="break-words">{entry.message}</Typography.Text>
                      {renderExtras(entry.extras)}
                    </>
                  ) : (
                    <Typography.Text className="break-words">{entry.message}</Typography.Text>
                  )}
                </Flex>
              </MobileCard>
            </List.Item>
          )}
        />
      </Flex>
    );
  }

  // Desktop view using Table
  return (
    <Flex ref={scrollRef}>
      <Table<ParsedLogLine>
        columns={columns}
        dataSource={entries}
        rowKey="index"
        size="small"
        pagination={false}
        scroll={{ y: 250 }}
        data-testid="structured-log-table"
      />
    </Flex>
  );
};
