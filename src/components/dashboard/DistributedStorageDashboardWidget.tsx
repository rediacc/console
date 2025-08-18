import React from 'react';
import { Card, Row, Col, Statistic, Progress, Space, Typography, Empty, Tag, List, Tooltip } from 'antd';
import { 
  CloudServerOutlined, 
  DatabaseOutlined, 
  HddOutlined,
  CopyOutlined,
  TeamOutlined 
} from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import { theme } from 'antd';
import { useTheme } from '@/context/ThemeContext';
import { useComponentStyles } from '@/hooks/useComponentStyles';

const { Text, Title } = Typography;

interface DistributedStorageTeamBreakdown {
  TeamName: string;
  TotalMachines: number;
  AvailableMachines: number;
  ClusterMachines: number;
  ImageMachines: number;
  CloneMachines: number;
}

interface DistributedStorageStats {
  total_machines: number;
  available_machines: number;
  cluster_assigned_machines: number;
  image_assigned_machines: number;
  clone_assigned_machines: number;
  truly_available_machines: number;
  available_percentage: number;
  cluster_percentage: number;
  image_percentage: number;
  clone_percentage: number;
  total_clusters: number;
  active_clusters: number;
  avg_machines_per_cluster: number;
  team_breakdown: DistributedStorageTeamBreakdown[];
}

interface DistributedStorageDashboardWidgetProps {
  stats: DistributedStorageStats;
}

const DistributedStorageDashboardWidget: React.FC<DistributedStorageDashboardWidgetProps> = ({ stats }) => {
  const { t } = useTranslation(['common', 'distributedStorage']);
  const { theme: currentTheme } = useTheme();
  const { token } = theme.useToken();
  const styles = useComponentStyles();

  if (!stats) {
    return null;
  }

  const getAssignmentColor = (type: 'available' | 'cluster' | 'image' | 'clone') => {
    switch (type) {
      case 'available':
        return token.colorSuccess;
      case 'cluster':
        return token.colorInfo;
      case 'image':
        return token.colorWarning;
      case 'clone':
        return '#fa8c16'; // Orange
      default:
        return token.colorTextSecondary;
    }
  };

  const assignmentData = [
    {
      type: 'available',
      label: t('distributedStorage:assignmentStatus.available'),
      count: stats.truly_available_machines,
      percentage: Math.round((stats.truly_available_machines / stats.total_machines) * 100),
      icon: <CloudServerOutlined />,
    },
    {
      type: 'cluster',
      label: t('distributedStorage:assignmentStatus.cluster'),
      count: stats.cluster_assigned_machines,
      percentage: stats.cluster_percentage,
      icon: <DatabaseOutlined />,
    },
    {
      type: 'image',
      label: t('distributedStorage:assignmentStatus.image'),
      count: stats.image_assigned_machines,
      percentage: stats.image_percentage,
      icon: <HddOutlined />,
    },
    {
      type: 'clone',
      label: t('distributedStorage:assignmentStatus.clone'),
      count: stats.clone_assigned_machines,
      percentage: stats.clone_percentage,
      icon: <CopyOutlined />,
    },
  ];

  return (
    <Card
      data-testid="ds-widget-card"
      title={
        <Space style={styles.flexStart}>
          <CloudServerOutlined style={styles.icon.medium} />
          <span style={styles.heading4}>{t('distributedStorage:dashboard.title')}</span>
        </Space>
      }
      extra={
        <Text type="secondary" style={styles.caption}>
          {t('distributedStorage:dashboard.subtitle', { total: stats.total_machines })}
        </Text>
      }
      style={{
        ...styles.card,
        border: '1px solid var(--color-border-secondary)'
      }}
    >
      <Space direction="vertical" size="large" style={{ width: '100%', ...styles.padding.md }}>
        {/* Machine Assignment Overview */}
        <Row gutter={[16, 16]}>
          {assignmentData.map((item) => (
            <Col key={item.type} xs={12} sm={12} md={6}>
              <Card 
                data-testid={`ds-widget-stat-${item.type}`}
                size="small" 
                style={{ 
                  textAlign: 'center',
                  borderColor: getAssignmentColor(item.type as any),
                  borderRadius: 'var(--border-radius-lg)',
                  backgroundColor: 'var(--color-bg-container)',
                  boxShadow: 'var(--shadow-sm)',
                  ...styles.hoverEffect
                }}
              >
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <div style={{ 
                    fontSize: styles.icon.xlarge.fontSize, 
                    color: getAssignmentColor(item.type as any) 
                  }}>
                    {item.icon}
                  </div>
                  <Statistic
                    data-testid={`ds-widget-stat-value-${item.type}`}
                    title={<span style={styles.label}>{item.label}</span>}
                    value={item.count}
                    suffix={
                      <Text type="secondary" style={styles.caption}>
                        ({item.percentage}%)
                      </Text>
                    }
                    valueStyle={{ 
                      ...styles.heading3,
                      color: getAssignmentColor(item.type as any)
                    }}
                  />
                </Space>
              </Card>
            </Col>
          ))}
        </Row>

        {/* Cluster Summary */}
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <div 
              data-testid="ds-widget-cluster-summary"
              style={{ 
                ...styles.padding.md, 
                backgroundColor: 'var(--color-bg-container)', 
                borderRadius: 'var(--border-radius-lg)',
                border: '1px solid var(--color-border-secondary)',
                boxShadow: 'var(--shadow-sm)'
              }}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Text strong style={styles.heading5}>{t('distributedStorage:dashboard.clusterSummary')}</Text>
                <Row gutter={16}>
                  <Col span={12}>
                    <Statistic
                      data-testid="ds-widget-stat-total-clusters"
                      title={<span style={styles.label}>{t('distributedStorage:dashboard.totalClusters')}</span>}
                      value={stats.total_clusters}
                      valueStyle={styles.heading4}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      data-testid="ds-widget-stat-avg-machines"
                      title={<span style={styles.label}>{t('distributedStorage:dashboard.avgMachinesPerCluster')}</span>}
                      value={stats.avg_machines_per_cluster}
                      precision={1}
                      valueStyle={styles.heading4}
                    />
                  </Col>
                </Row>
              </Space>
            </div>
          </Col>

          {/* Machine Utilization */}
          <Col xs={24} md={12}>
            <div 
              data-testid="ds-widget-machine-utilization"
              style={{ 
                ...styles.padding.md, 
                backgroundColor: 'var(--color-bg-container)', 
                borderRadius: 'var(--border-radius-lg)',
                border: '1px solid var(--color-border-secondary)',
                boxShadow: 'var(--shadow-sm)'
              }}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text strong style={styles.heading5}>{t('distributedStorage:dashboard.machineUtilization')}</Text>
                <Progress
                  data-testid="ds-widget-progress-utilization"
                  percent={Math.round(((stats.total_machines - stats.truly_available_machines) / stats.total_machines) * 100)}
                  strokeColor={{
                    '0%': token.colorPrimary,
                    '100%': token.colorSuccess,
                  }}
                  format={(percent) => `${percent}% ${t('common:utilized')}`}
                />
                <Text type="secondary" style={styles.caption}>
                  {t('distributedStorage:dashboard.utilizationDetails', {
                    used: stats.total_machines - stats.truly_available_machines,
                    total: stats.total_machines
                  })}
                </Text>
              </Space>
            </div>
          </Col>
        </Row>

        {/* Team Breakdown */}
        {stats.team_breakdown && stats.team_breakdown.length > 0 && (
          <div data-testid="ds-widget-team-breakdown">
            <Space style={styles.marginBottom.sm}>
              <TeamOutlined style={styles.icon.medium} />
              <Text strong style={styles.heading5}>{t('distributedStorage:dashboard.teamBreakdown')}</Text>
            </Space>
            <List
              data-testid="ds-widget-team-list"
              size="small"
              dataSource={stats.team_breakdown}
              renderItem={(team) => (
                <List.Item
                  data-testid={`ds-widget-team-item-${team.TeamName.toLowerCase().replace(/\s+/g, '-')}`}
                  style={{ 
                    ...styles.padding.sm,
                    backgroundColor: 'var(--color-bg-container)',
                    marginBottom: '8px',
                    borderRadius: 'var(--border-radius-md)',
                    border: '1px solid var(--color-border-secondary)',
                    boxShadow: 'var(--shadow-sm)'
                  }}
                >
                  <div style={{ width: '100%' }}>
                    <div style={{ 
                      ...styles.flexBetween,
                      ...styles.marginBottom.xs
                    }}>
                      <Text strong style={styles.label}>{team.TeamName}</Text>
                      <Text type="secondary" style={styles.caption}>{team.TotalMachines} machines</Text>
                    </div>
                    <Space wrap>
                      <Tooltip title={t('distributedStorage:assignmentStatus.available')}>
                        <Tag data-testid={`ds-widget-team-tag-available-${team.TeamName.toLowerCase().replace(/\s+/g, '-')}`} color="success">{team.AvailableMachines} available</Tag>
                      </Tooltip>
                      {team.ClusterMachines > 0 && (
                        <Tooltip title={t('distributedStorage:assignmentStatus.cluster')}>
                          <Tag data-testid={`ds-widget-team-tag-cluster-${team.TeamName.toLowerCase().replace(/\s+/g, '-')}`} color="blue">{team.ClusterMachines} cluster</Tag>
                        </Tooltip>
                      )}
                      {team.ImageMachines > 0 && (
                        <Tooltip title={t('distributedStorage:assignmentStatus.image')}>
                          <Tag data-testid={`ds-widget-team-tag-image-${team.TeamName.toLowerCase().replace(/\s+/g, '-')}`} color="purple">{team.ImageMachines} image</Tag>
                        </Tooltip>
                      )}
                      {team.CloneMachines > 0 && (
                        <Tooltip title={t('distributedStorage:assignmentStatus.clone')}>
                          <Tag data-testid={`ds-widget-team-tag-clone-${team.TeamName.toLowerCase().replace(/\s+/g, '-')}`} color="orange">{team.CloneMachines} clone</Tag>
                        </Tooltip>
                      )}
                    </Space>
                  </div>
                </List.Item>
              )}
            />
          </div>
        )}
      </Space>
    </Card>
  );
};

export default DistributedStorageDashboardWidget;