import { Form, Select, Space, Tag, Typography } from 'antd';
import type { FormInstance } from 'antd/es/form';
import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiOutlined, EnvironmentOutlined, TeamOutlined } from '@/utils/optimizedIcons';
import type { ResourceType } from '../types';

interface DropdownData {
  teams?: { value: string; label: string }[];
  regions?: { value: string; label: string }[];
  bridgesByRegion?: {
    regionName: string;
    bridges: { value: string; label: string }[];
  }[];
}

interface InfrastructurePillsProps {
  resourceType: ResourceType;
  mode: 'create' | 'edit' | 'vault';
  uiMode: 'simple' | 'expert';
  form: FormInstance;
  dropdownData?: DropdownData;
  getFilteredBridges: (regionName: string | null) => { value: string; label: string }[];
}

/**
 * Displays infrastructure settings (Team, Region, Bridge) as pills/tags.
 * - Simple mode: Static tags showing current values
 * - Expert mode: Selectable tags with dropdown functionality
 *
 * Only shown for machine resource type during creation.
 */
export const InfrastructurePills: React.FC<InfrastructurePillsProps> = ({
  resourceType,
  mode,
  uiMode,
  form,
  dropdownData,
  getFilteredBridges,
}) => {
  const { t } = useTranslation(['resources', 'machines', 'common', 'system']);

  const isSimpleMode = uiMode === 'simple';
  const isMachineCreate = resourceType === 'machine' && mode === 'create';

  // Watch form values - must be called unconditionally (React hooks rule)
  const teamValue = Form.useWatch('teamName', form) ?? (isSimpleMode ? 'Private Team' : '');
  const regionValue = Form.useWatch('regionName', form) ?? (isSimpleMode ? 'Default Region' : '');
  const bridgeValue = Form.useWatch('bridgeName', form) ?? (isSimpleMode ? 'Global Bridges' : '');

  const teamOptions = dropdownData?.teams ?? [];
  const regionOptions = dropdownData?.regions ?? [];
  const bridgeOptions = getFilteredBridges(regionValue ?? null);

  // Handle region change - update available bridges and clear invalid selection
  useEffect(() => {
    if (!regionValue || isSimpleMode || !isMachineCreate) return;

    const currentBridge = form.getFieldValue('bridgeName') as string | undefined;
    const availableBridges = getFilteredBridges(regionValue);

    // If current bridge is not valid for the new region, clear it or select first available
    if (currentBridge && !availableBridges.find((b) => b.value === currentBridge)) {
      if (availableBridges.length > 0) {
        form.setFieldValue('bridgeName', availableBridges[0].value);
      } else {
        form.setFieldValue('bridgeName', '');
      }
    } else if (!currentBridge && availableBridges.length > 0) {
      // Auto-select first bridge if none selected
      form.setFieldValue('bridgeName', availableBridges[0].value);
    }
  }, [regionValue, form, getFilteredBridges, isSimpleMode, isMachineCreate]);

  // Only show for machine creation - return null after all hooks are called
  if (!isMachineCreate) {
    return null;
  }

  // Simple mode: Static tags
  if (isSimpleMode) {
    return (
      <Space size="small" wrap className="mb-4" data-testid="infrastructure-pills-simple">
        <Tag icon={<TeamOutlined />} color="blue">
          {teamValue ?? t('defaults.privateTeam')}
        </Tag>
        <Tag icon={<EnvironmentOutlined />} color="green">
          {regionValue ?? t('defaults.defaultRegion')}
        </Tag>
        <Tag icon={<ApiOutlined />} color="purple">
          {bridgeValue ?? t('defaults.globalBridges')}
        </Tag>
        {/* Hidden form fields to maintain form state */}
        <Form.Item name="teamName" hidden noStyle>
          <Typography.Text />
        </Form.Item>
        <Form.Item name="regionName" hidden noStyle>
          <Typography.Text />
        </Form.Item>
        <Form.Item name="bridgeName" hidden noStyle>
          <Typography.Text />
        </Form.Item>
      </Space>
    );
  }

  // Expert mode: Selectable pills with dropdowns
  return (
    <Space size="small" wrap className="mb-4" data-testid="infrastructure-pills-expert">
      {/* Team Selection */}
      <Form.Item
        name="teamName"
        noStyle
        rules={[{ required: true, message: t('teams.placeholders.selectTeam') }]}
      >
        <Select
          data-testid="infrastructure-pill-team"
          placeholder={t('teams.placeholders.selectTeam')}
          className="min-w-36"
          size="small"
          variant="filled"
          options={teamOptions}
          suffixIcon={<TeamOutlined />}
          popupMatchSelectWidth={false}
        />
      </Form.Item>

      {/* Region Selection */}
      <Form.Item
        name="regionName"
        noStyle
        rules={[{ required: true, message: t('regions.placeholders.selectRegion') }]}
      >
        <Select
          data-testid="infrastructure-pill-region"
          placeholder={t('regions.placeholders.selectRegion')}
          className="min-w-36"
          size="small"
          variant="filled"
          options={regionOptions}
          suffixIcon={<EnvironmentOutlined />}
          popupMatchSelectWidth={false}
        />
      </Form.Item>

      {/* Bridge Selection */}
      <Form.Item
        name="bridgeName"
        noStyle
        rules={[{ required: true, message: t('bridges.placeholders.selectBridge') }]}
      >
        <Select
          data-testid="infrastructure-pill-bridge"
          placeholder={
            regionValue
              ? t('bridges.placeholders.selectBridge')
              : t('bridges.placeholders.selectRegionFirst')
          }
          className="min-w-36"
          size="small"
          variant="filled"
          options={bridgeOptions}
          disabled={!regionValue}
          suffixIcon={<ApiOutlined />}
          popupMatchSelectWidth={false}
        />
      </Form.Item>
    </Space>
  );
};
