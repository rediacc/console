import React from 'react';
import { Form, Popover, Slider, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { RediaccText } from '@/components/ui';
import { ExclamationCircleOutlined, WarningOutlined } from '@/utils/optimizedIcons';
import {
  PriorityAlert,
  PriorityAlertDetail,
  PriorityAlertNote,
  PriorityHelpIcon,
  PriorityLegendRow,
  PriorityLegendTag,
  PriorityPopoverContent,
  PriorityLabelBlock,
  PriorityStatusTag,
  PriorityTagWrapper,
} from '../styles';

interface PrioritySelectorProps {
  priority: number;
  onPriorityChange: (priority: number) => void;
  priorityLegendItems: Array<{
    level: number;
    label: string;
    description: string;
  }>;
  getPriorityLabel: (priority: number) => string;
}

const PrioritySelector: React.FC<PrioritySelectorProps> = ({
  priority,
  onPriorityChange,
  priorityLegendItems,
  getPriorityLabel,
}) => {
  const { t } = useTranslation(['functions']);

  return (
    <Form.Item
      label={
        <Space size={4}>
          {t('functions:priority')}
          <Popover
            content={
              <PriorityPopoverContent>
                <PriorityLabelBlock>
                  <RediaccText variant="title">{t('functions:priorityPopoverLevels')}</RediaccText>
                </PriorityLabelBlock>
                {priorityLegendItems.map((item) => (
                  <PriorityLegendRow key={item.level}>
                    <PriorityLegendTag $level={item.level}>
                      P{item.level} ({item.label})
                    </PriorityLegendTag>
                    <RediaccText variant="description">{item.description}</RediaccText>
                  </PriorityLegendRow>
                ))}
              </PriorityPopoverContent>
            }
            title={t('functions:priorityPopoverTitle')}
            trigger="click"
          >
            <PriorityHelpIcon />
          </Popover>
        </Space>
      }
      help={t('functions:priorityHelp')}
    >
      <Slider
        min={1}
        max={5}
        value={priority}
        onChange={onPriorityChange}
        marks={{
          1: t('functions:priorityHigh'),
          3: t('functions:priorityNormal'),
          5: t('functions:priorityLow'),
        }}
        tooltip={{
          formatter: (value?: number) => {
            const labels = {
              1: t('functions:priorityHighest'),
              2: t('functions:priorityHigh'),
              3: t('functions:priorityNormal'),
              4: t('functions:priorityBelowNormal'),
              5: t('functions:priorityLow'),
            };
            return value ? `${labels[value as keyof typeof labels]} (${value})` : '';
          },
        }}
        data-testid="function-modal-priority-slider"
      />
      <PriorityTagWrapper>
        <PriorityStatusTag
          $priority={priority}
          icon={priority === 1 ? <ExclamationCircleOutlined /> : undefined}
        >
          {t('functions:currentPriority')}: {getPriorityLabel(priority)} ({priority})
        </PriorityStatusTag>
      </PriorityTagWrapper>
      {priority && (
        <PriorityAlert
          message={
            priority === 1
              ? t('functions:priorityHighestTimeout')
              : priority === 2
                ? t('functions:priorityHighWarning')
                : priority === 3
                  ? t('functions:priorityNormalWarning')
                  : priority === 4
                    ? t('functions:priorityLowWarning')
                    : t('functions:priorityLowestWarning')
          }
          description={
            priority === 1 ? (
              <>
                <PriorityAlertNote>
                  {t('functions:priorityHighestTimeoutWarning')}
                </PriorityAlertNote>
                <PriorityAlertDetail>
                  {t('functions:priorityHighestDescription')}
                </PriorityAlertDetail>
              </>
            ) : priority === 2 ? (
              t('functions:priorityHighDescription')
            ) : priority === 3 ? (
              t('functions:priorityNormalDescription')
            ) : priority === 4 ? (
              t('functions:priorityLowDescription')
            ) : (
              t('functions:priorityLowestDescription')
            )
          }
          variant={
            priority === 1
              ? 'error'
              : priority === 2
                ? 'warning'
                : priority === 3
                  ? 'info'
                  : 'success'
          }
          showIcon
          icon={
            priority === 1 ? (
              <ExclamationCircleOutlined />
            ) : priority === 2 ? (
              <WarningOutlined />
            ) : undefined
          }
        />
      )}
    </Form.Item>
  );
};

export default PrioritySelector;
