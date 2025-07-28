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
      title={
        <Space>
          <CloudServerOutlined />
          <span>{t('distributedStorage:dashboard.title')}</span>
        </Space>
      }
      extra={
        <Text type="secondary">
          {t('distributedStorage:dashboard.subtitle', { total: stats.total_machines })}
        </Text>
      }
    >
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Machine Assignment Overview */}
        <Row gutter={[16, 16]}>
          {assignmentData.map((item) => (
            <Col key={item.type} xs={12} sm={12} md={6}>
              <Card 
                size="small" 
                style={{ 
                  textAlign: 'center',
                  borderColor: getAssignmentColor(item.type as any),
                  backgroundColor: currentTheme === 'dark' 
                    ? token.colorBgContainer 
                    : token.colorBgLayout 
                }}
              >
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <div style={{ fontSize: 24, color: getAssignmentColor(item.type as any) }}>
                    {item.icon}
                  </div>
                  <Statistic
                    title={item.label}
                    value={item.count}
                    suffix={
                      <Text type="secondary" style={{ fontSize: 14 }}>
                        ({item.percentage}%)
                      </Text>
                    }
                    valueStyle={{ 
                      fontSize: 20,
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
            <div style={{ 
              padding: '16px', 
              backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout, 
              borderRadius: 8,
              border: `1px solid ${token.colorBorder}`
            }}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Text strong>{t('distributedStorage:dashboard.clusterSummary')}</Text>
                <Row gutter={16}>
                  <Col span={12}>
                    <Statistic
                      title={t('distributedStorage:dashboard.totalClusters')}
                      value={stats.total_clusters}
                      valueStyle={{ fontSize: 18 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title={t('distributedStorage:dashboard.avgMachinesPerCluster')}
                      value={stats.avg_machines_per_cluster}
                      precision={1}
                      valueStyle={{ fontSize: 18 }}
                    />
                  </Col>
                </Row>
              </Space>
            </div>
          </Col>

          {/* Machine Utilization */}
          <Col xs={24} md={12}>
            <div style={{ 
              padding: '16px', 
              backgroundColor: currentTheme === 'dark' ? token.colorBgContainer : token.colorBgLayout, 
              borderRadius: 8,
              border: `1px solid ${token.colorBorder}`
            }}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Text strong>{t('distributedStorage:dashboard.machineUtilization')}</Text>
                <Progress
                  percent={Math.round(((stats.total_machines - stats.truly_available_machines) / stats.total_machines) * 100)}
                  strokeColor={{
                    '0%': token.colorPrimary,
                    '100%': token.colorSuccess,
                  }}
                  format={(percent) => `${percent}% ${t('common:utilized')}`}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
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
          <div>
            <Space style={{ marginBottom: 12 }}>
              <TeamOutlined />
              <Text strong>{t('distributedStorage:dashboard.teamBreakdown')}</Text>
            </Space>
            <List
              size="small"
              dataSource={stats.team_breakdown}
              renderItem={(team) => (
                <List.Item
                  style={{ 
                    paddingLeft: 12, 
                    paddingRight: 12,
                    backgroundColor: currentTheme === 'dark' 
                      ? token.colorBgContainer 
                      : token.colorBgLayout,
                    marginBottom: 8,
                    borderRadius: 6,
                    border: `1px solid ${token.colorBorder}`
                  }}
                >
                  <div style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <Text strong>{team.TeamName}</Text>
                      <Text type="secondary">{team.TotalMachines} machines</Text>
                    </div>
                    <Space wrap>
                      <Tooltip title={t('distributedStorage:assignmentStatus.available')}>
                        <Tag color="success">{team.AvailableMachines} available</Tag>
                      </Tooltip>
                      {team.ClusterMachines > 0 && (
                        <Tooltip title={t('distributedStorage:assignmentStatus.cluster')}>
                          <Tag color="blue">{team.ClusterMachines} cluster</Tag>
                        </Tooltip>
                      )}
                      {team.ImageMachines > 0 && (
                        <Tooltip title={t('distributedStorage:assignmentStatus.image')}>
                          <Tag color="purple">{team.ImageMachines} image</Tag>
                        </Tooltip>
                      )}
                      {team.CloneMachines > 0 && (
                        <Tooltip title={t('distributedStorage:assignmentStatus.clone')}>
                          <Tag color="orange">{team.CloneMachines} clone</Tag>
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