import React from 'react'
import { Card, Row, Col, Statistic, Spin } from 'antd'
import {
  DesktopOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  HddOutlined,
  CopyOutlined,
  ReloadOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useMachines } from '@/api/queries/machines'
import { useGetMachineAssignmentStatus } from '@/api/queries/distributedStorage'
import { Machine } from '@/types'

interface MachineAvailabilitySummaryProps {
  teamFilter?: string | string[]
  onRefresh?: () => void
}

interface MachineStats {
  total: number
  available: number
  cluster: number
  image: number
  clone: number
}

export const MachineAvailabilitySummary: React.FC<MachineAvailabilitySummaryProps> = ({
  teamFilter,
  onRefresh
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines'])
  const { data: machines = [], isLoading, refetch } = useMachines(teamFilter)

  // Calculate statistics
  const stats = React.useMemo<MachineStats>(() => {
    const result: MachineStats = {
      total: machines.length,
      available: 0,
      cluster: 0,
      image: 0,
      clone: 0
    }

    // Count machines by assignment type
    machines.forEach((machine: Machine) => {
      // If machine has distributedStorageClusterName, it's assigned to a cluster
      if (machine.distributedStorageClusterName) {
        result.cluster++
      } else {
        // For now, we'll count it as available if no cluster assignment
        // In a real implementation, we'd check image and clone assignments too
        result.available++
      }
    })

    return result
  }, [machines])

  const handleRefresh = () => {
    refetch()
    onRefresh?.()
  }

  if (isLoading) {
    return (
      <Card style={{ marginBottom: 16 }}>
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Spin />
        </div>
      </Card>
    )
  }

  return (
    <Card 
      title={t('machines.summary.title')}
      extra={
        <ReloadOutlined 
          style={{ cursor: 'pointer' }} 
          onClick={handleRefresh}
          spin={isLoading}
        />
      }
      style={{ marginBottom: 16 }}
    >
      <Row gutter={16}>
        <Col xs={24} sm={12} md={8} lg={4}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={t('machines.summary.total')}
              value={stats.total}
              prefix={<DesktopOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        
        <Col xs={24} sm={12} md={8} lg={5}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={t('machines.summary.available')}
              value={stats.available}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
              suffix={
                <span style={{ fontSize: 14, color: '#666' }}>
                  ({stats.total > 0 ? Math.round((stats.available / stats.total) * 100) : 0}%)
                </span>
              }
            />
          </Card>
        </Col>
        
        <Col xs={24} sm={12} md={8} lg={5}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={t('machines.summary.assignedToClusters')}
              value={stats.cluster}
              prefix={<CloudServerOutlined />}
              valueStyle={{ color: '#1890ff' }}
              suffix={
                <span style={{ fontSize: 14, color: '#666' }}>
                  ({stats.total > 0 ? Math.round((stats.cluster / stats.total) * 100) : 0}%)
                </span>
              }
            />
          </Card>
        </Col>
        
        <Col xs={24} sm={12} md={8} lg={5}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={t('machines.summary.assignedToImages')}
              value={stats.image}
              prefix={<HddOutlined />}
              valueStyle={{ color: '#fa8c16' }}
              suffix={
                <span style={{ fontSize: 14, color: '#666' }}>
                  ({stats.total > 0 ? Math.round((stats.image / stats.total) * 100) : 0}%)
                </span>
              }
            />
          </Card>
        </Col>
        
        <Col xs={24} sm={12} md={8} lg={5}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={t('machines.summary.assignedToClones')}
              value={stats.clone}
              prefix={<CopyOutlined />}
              valueStyle={{ color: '#722ed1' }}
              suffix={
                <span style={{ fontSize: 14, color: '#666' }}>
                  ({stats.total > 0 ? Math.round((stats.clone / stats.total) * 100) : 0}%)
                </span>
              }
            />
          </Card>
        </Col>
      </Row>
    </Card>
  )
}