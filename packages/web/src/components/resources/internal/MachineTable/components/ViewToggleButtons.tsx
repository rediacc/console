import React from 'react';
import { Button, Flex, Space, Tooltip, Typography } from 'antd';
import {
  BranchesOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  DesktopOutlined,
  GlobalOutlined,
  InboxOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons';
import type { GroupByMode } from '../types';
import type { TFunction } from 'i18next';

interface ViewToggleButtonsProps {
  groupBy: GroupByMode;
  setGroupBy: (mode: GroupByMode) => void;
  uiMode: string;
  isExpertMode: boolean;
  t: TFunction;
}

export const ViewToggleButtons: React.FC<ViewToggleButtonsProps> = ({
  groupBy,
  setGroupBy,
  uiMode,
  isExpertMode,
  t,
}) => {
  // In simple mode, hide all grouping buttons
  if (uiMode === 'simple') {
    return null;
  }

  // In expert/normal mode, show all grouping buttons
  return (
    <Flex>
      <Space wrap size="small">
        <Tooltip title={t('machines:machine')}>
          <Button
            // eslint-disable-next-line no-restricted-syntax
            style={{ minWidth: 42 }}
            type={groupBy === 'machine' ? 'primary' : 'default'}
            icon={<DesktopOutlined />}
            onClick={() => setGroupBy('machine')}
            data-testid="machine-view-toggle-machine"
            aria-label={t('machines:machine')}
          />
        </Tooltip>

        <Typography.Text
          // eslint-disable-next-line no-restricted-syntax
          style={{ width: 1, height: 24 }}
        />

        <Tooltip title={t('machines:groupByBridge')}>
          <Button
            // eslint-disable-next-line no-restricted-syntax
            style={{ minWidth: 42 }}
            type={groupBy === 'bridge' ? 'primary' : 'default'}
            icon={<CloudServerOutlined />}
            onClick={() => setGroupBy('bridge')}
            data-testid="machine-view-toggle-bridge"
            aria-label={t('machines:groupByBridge')}
          />
        </Tooltip>

        <Tooltip title={t('machines:groupByTeam')}>
          <Button
            // eslint-disable-next-line no-restricted-syntax
            style={{ minWidth: 42 }}
            type={groupBy === 'team' ? 'primary' : 'default'}
            icon={<TeamOutlined />}
            onClick={() => setGroupBy('team')}
            data-testid="machine-view-toggle-team"
            aria-label={t('machines:groupByTeam')}
          />
        </Tooltip>

        {isExpertMode && (
          <Tooltip title={t('machines:groupByRegion')}>
            <Button
              // eslint-disable-next-line no-restricted-syntax
              style={{ minWidth: 42 }}
              type={groupBy === 'region' ? 'primary' : 'default'}
              icon={<GlobalOutlined />}
              onClick={() => setGroupBy('region')}
              data-testid="machine-view-toggle-region"
              aria-label={t('machines:groupByRegion')}
            />
          </Tooltip>
        )}

        <Tooltip title={t('machines:groupByRepository')}>
          <Button
            // eslint-disable-next-line no-restricted-syntax
            style={{ minWidth: 42 }}
            type={groupBy === 'repository' ? 'primary' : 'default'}
            icon={<InboxOutlined />}
            onClick={() => setGroupBy('repository')}
            data-testid="machine-view-toggle-repo"
            aria-label={t('machines:groupByRepository')}
          />
        </Tooltip>

        <Tooltip title={t('machines:groupByStatus')}>
          <Button
            // eslint-disable-next-line no-restricted-syntax
            style={{ minWidth: 42 }}
            type={groupBy === 'status' ? 'primary' : 'default'}
            icon={<DashboardOutlined />}
            onClick={() => setGroupBy('status')}
            data-testid="machine-view-toggle-status"
            aria-label={t('machines:groupByStatus')}
          />
        </Tooltip>

        <Tooltip title={t('machines:groupByGrand')}>
          <Button
            // eslint-disable-next-line no-restricted-syntax
            style={{ minWidth: 42 }}
            type={groupBy === 'grand' ? 'primary' : 'default'}
            icon={<BranchesOutlined />}
            onClick={() => setGroupBy('grand')}
            data-testid="machine-view-toggle-grand"
            aria-label={t('machines:groupByGrand')}
          />
        </Tooltip>
      </Space>
    </Flex>
  );
};
