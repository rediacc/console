import React, { useState, useEffect, useRef } from 'react'
import { Card, Spin, Alert, Space, Typography, Radio, Button, Tooltip, Statistic, Row, Col, Select, Checkbox } from 'antd'
import { 
  FullscreenOutlined, 
  FullscreenExitOutlined, 
  ReloadOutlined,
  CloudOutlined,
  TeamOutlined,
  UserOutlined,
  ApiOutlined,
  GlobalOutlined,
  InboxOutlined,
  ScheduleOutlined,
  FilterOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useCompanyArchitecture } from '@/api/queries/architecture'
import { useTheme } from '@/context/ThemeContext'
import * as d3 from 'd3'

const { Title, Text } = Typography

interface GraphNode extends d3.SimulationNodeDatum {
  nodeType: string
  nodeId: string
  name: string
  label: string
  hierarchyLevel: string
  [key: string]: any
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  relationshipType: string
  label: string
}

const ArchitecturePage: React.FC = () => {
  const { t } = useTranslation('system')
  const { data, isLoading, error, refetch } = useCompanyArchitecture()
  const [viewMode, setViewMode] = useState<'hierarchy' | 'force' | 'radial'>('hierarchy')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [selectedEntityTypes, setSelectedEntityTypes] = useState<string[]>([
    'company', 'user', 'team', 'region', 'bridge', 'machine', 'repository', 'schedule', 'storage'
  ])
  const svgRef = useRef<SVGSVGElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const { theme } = useTheme()

  // Available entity types for filtering
  const entityTypes = [
    { value: 'company', label: t('architecture.nodeCompany'), icon: '🏢' },
    { value: 'user', label: t('architecture.nodeUser'), icon: '👤' },
    { value: 'team', label: t('architecture.nodeTeam'), icon: '👥' },
    { value: 'region', label: t('architecture.nodeRegion'), icon: '🌍' },
    { value: 'bridge', label: t('architecture.nodeBridge'), icon: '🌉' },
    { value: 'machine', label: t('architecture.nodeMachine'), icon: '💻' },
    { value: 'repository', label: t('architecture.nodeRepository'), icon: '📦' },
    { value: 'schedule', label: t('architecture.nodeSchedule'), icon: '📅' },
    { value: 'storage', label: t('architecture.nodeStorage'), icon: '💾' },
  ]

  // Convert the nested node structure to a flat array with filtering
  const flattenNodes = (nodes: any, filterTypes: string[]): GraphNode[] => {
    const flatNodes: GraphNode[] = []
    
    // Process each node type
    Object.entries(nodes).forEach(([type, nodeArray]) => {
      if (Array.isArray(nodeArray) && nodeArray.length > 0) {
        nodeArray.forEach((node: any) => {
          // Ensure nodeType is set correctly - some nodes already have it
          const nodeType = node.nodeType || type.slice(0, -1) // Use existing nodeType or derive from key
          
          // Only include if the node type is in the filter
          if (filterTypes.includes(nodeType)) {
            const nodeWithType = {
              ...node,
              nodeType: nodeType,
            }
            flatNodes.push(nodeWithType)
          }
        })
      }
    })
    
    return flatNodes
  }

  // Convert relationships to links
  const flattenRelationships = (relationships: any, nodes: GraphNode[]): GraphLink[] => {
    const links: GraphLink[] = []
    const nodeMap = new Map(nodes.map(n => [n.nodeId, n]))
    
    // Process each relationship type
    Object.entries(relationships).forEach(([, relArray]) => {
      if (Array.isArray(relArray)) {
        relArray.forEach((rel: any) => {
          const source = nodeMap.get(rel.source)
          const target = nodeMap.get(rel.target)
          if (source && target) {
            links.push({
              source,
              target,
              relationshipType: rel.relationshipType,
              label: rel.label,
            })
          }
        })
      }
    })
    
    return links
  }

  // Get icon for node type
  const getNodeIcon = (nodeType: string) => {
    const icons: Record<string, string> = {
      company: '🏢',
      user: '👤',
      team: '👥',
      region: '📍',
      bridge: '🔌',
      machine: '💻',
      repository: '📁',
      schedule: '📅',
      storage: '☁️',
    }
    return icons[nodeType] || '📌'
  }

  // Get color for node type
  const getNodeColor = (nodeType: string) => {
    const lightColors: Record<string, string> = {
      company: '#e0e0e0',
      user: '#d6d6d6',
      team: '#cccccc',
      region: '#c2c2c2',
      bridge: '#b8b8b8',
      machine: '#aeaeae',
      repository: '#a4a4a4',
      schedule: '#9a9a9a',
      storage: '#909090',
    }
    
    const darkColors: Record<string, string> = {
      company: '#4a5568',
      user: '#5a6778',
      team: '#6a7788',
      region: '#7a8798',
      bridge: '#8a97a8',
      machine: '#9aa7b8',
      repository: '#aab7c8',
      schedule: '#bac7d8',
      storage: '#cad7e8',
    }
    
    const colors = theme === 'dark' ? darkColors : lightColors
    return colors[nodeType] || (theme === 'dark' ? '#6a7788' : '#cccccc')
  }

  // Render D3 visualization
  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return

    const width = containerRef.current.clientWidth || 800
    const height = 600

    const nodes = flattenNodes(data.nodes, selectedEntityTypes)
    const links = flattenRelationships(data.relationships, nodes)
    
    // Check if we have nodes
    if (nodes.length === 0) {
      // Clear the svg and show empty state
      d3.select(svgRef.current).selectAll('*').remove()
      
      const svg = d3.select(svgRef.current)
        .attr('width', width)
        .attr('height', height)
      
      svg.append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .style('fill', '#999')
        .text(t('architecture.noEntitiesSelected', { ns: 'system' }))
      
      return
    }

    // Clear previous visualization
    d3.select(svgRef.current).selectAll('*').remove()

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height)

    // Add zoom behavior
    const g = svg.append('g')
      .attr('class', 'main-group')
    
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      })

    svg.call(zoom)

    // Create arrow markers for directed edges
    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('path')
      .attr('d', 'M 0,-5 L 10,0 L 0,5')
      .attr('fill', theme === 'dark' ? '#999' : '#666')

    if (viewMode === 'force') {
      // Force-directed layout
      
      // Initialize node positions
      nodes.forEach((d) => {
        d.x = width / 2 + (Math.random() - 0.5) * 100
        d.y = height / 2 + (Math.random() - 0.5) * 100
      })
      
      // Create a copy of links for the simulation
      const simulationLinks = links.map(d => ({
        source: (d.source as GraphNode).nodeId,
        target: (d.target as GraphNode).nodeId,
        relationshipType: d.relationshipType,
        label: d.label
      }))
      
      const simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(simulationLinks).id((d: any) => d.nodeId).distance(150))
        .force('charge', d3.forceManyBody().strength(-500))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(40))
        .force('x', d3.forceX(width / 2).strength(0.1))
        .force('y', d3.forceY(height / 2).strength(0.1))

      // Create links
      const link = g.append('g')
        .selectAll('line')
        .data(simulationLinks)
        .join('line')
        .attr('stroke', '#cccccc')
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', 2)
        .attr('marker-end', 'url(#arrowhead)')

      // Create nodes
      const node = g.append('g')
        .selectAll('g')
        .data(nodes)
        .join('g')
        .call(d3.drag<SVGGElement, GraphNode, GraphNode>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          })
        )

      // Add circles for nodes
      node.append('circle')
        .attr('r', 20)
        .attr('fill', (d) => getNodeColor(d.nodeType))
        .attr('stroke', '#333')
        .attr('stroke-width', 2)

      // Add icons
      node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d) => getNodeIcon(d.nodeType))

      // Add labels
      node.append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', '#333')
        .text((d) => d.name)

      // Add tooltips
      node.append('title')
        .text((d) => {
          const details = [`Type: ${d.nodeType}`, `Name: ${d.name}`]
          if (d.nodeType === 'team' && d.memberCount !== undefined) {
            details.push(`Members: ${d.memberCount}`)
            details.push(`Machines: ${d.machineCount || 0}`)
          }
          if (d.nodeType === 'machine' && d.queueCount !== undefined) {
            details.push(`Queue Items: ${d.queueCount}`)
            details.push(`Region: ${d.regionName}`)
          }
          return details.join('\n')
        })

      simulation.on('tick', () => {
        link
          .attr('x1', (d: any) => d.source.x || 0)
          .attr('y1', (d: any) => d.source.y || 0)
          .attr('x2', (d: any) => d.target.x || 0)
          .attr('y2', (d: any) => d.target.y || 0)

        node.attr('transform', (d) => `translate(${d.x || 0},${d.y || 0})`)
      })
      
      // Run the simulation
      simulation.alpha(1).restart()

    } else if (viewMode === 'hierarchy') {
      // Hierarchical layout
      const companyNode = nodes.find(n => n.nodeType === 'company')
      if (!companyNode) return

      // Build hierarchy data structure
      const hierarchyData = {
        ...companyNode,
        children: [] as any[],
      }

      // Get all node types
      const teams = nodes.filter(n => n.nodeType === 'team')
      const regions = nodes.filter(n => n.nodeType === 'region')
      const users = nodes.filter(n => n.nodeType === 'user')
      const bridges = nodes.filter(n => n.nodeType === 'bridge')
      const machines = nodes.filter(n => n.nodeType === 'machine')
      const repositories = nodes.filter(n => n.nodeType === 'repository')
      const schedules = nodes.filter(n => n.nodeType === 'schedule')
      const storages = nodes.filter(n => n.nodeType === 'storage')

      // Build teams branch with their related nodes
      const teamsBranch = teams.map(team => {
        const teamChildren = []
        
        // Add users that belong to this team based on relationships
        const teamUsers = users.filter(user => 
          links.some(link => 
            link.source === user && 
            link.target === team &&
            link.relationshipType === 'memberOf'
          )
        )
        teamChildren.push(...teamUsers)
        
        // Add machines for this team (if any)
        const teamMachines = machines.filter(m => m.parentTeam === team.nodeId)
        teamChildren.push(...teamMachines)
        
        // Add repositories for this team (if any)
        const teamRepos = repositories.filter(r => r.parentTeam === team.nodeId)
        teamChildren.push(...teamRepos)
        
        // Add schedules for this team (if any)
        const teamSchedules = schedules.filter(s => s.parentTeam === team.nodeId)
        teamChildren.push(...teamSchedules)
        
        // Add storages for this team (if any)
        const teamStorages = storages.filter(s => s.parentTeam === team.nodeId)
        teamChildren.push(...teamStorages)
        
        return {
          ...team,
          children: teamChildren.length > 0 ? teamChildren : [],
        }
      })

      // Build regions branch with bridges
      const regionsBranch = regions.map(region => {
        const regionBridges = bridges.filter(b => b.parentRegion === region.nodeId)
        
        // For each bridge, find its machines
        const bridgesWithMachines = regionBridges.map(bridge => ({
          ...bridge,
          children: machines.filter(m => m.parentBridge === bridge.nodeId),
        }))
        
        return {
          ...region,
          children: bridgesWithMachines,
        }
      })

      // Combine all branches
      hierarchyData.children = [...teamsBranch, ...regionsBranch]

      // If no children, add a placeholder
      if (hierarchyData.children.length === 0) {
        hierarchyData.children = [{ 
          nodeId: 'placeholder', 
          name: 'No child nodes', 
          nodeType: 'placeholder',
          hierarchyLevel: 'level1'
        }]
      }

      const root = d3.hierarchy(hierarchyData)
      const treeLayout = d3.tree<any>().size([width - 100, height - 100])
      const treeData = treeLayout(root)

      // Draw links
      g.append('g')
        .selectAll('path')
        .data(treeData.links())
        .join('path')
        .attr('d', d3.linkVertical<any, any>()
          .x((d: any) => d.x + 50)
          .y((d: any) => d.y + 50) as any
        )
        .attr('fill', 'none')
        .attr('stroke', '#cccccc')
        .attr('stroke-width', 2)

      // Draw nodes
      const node = g.append('g')
        .selectAll('g')
        .data(treeData.descendants())
        .join('g')
        .attr('transform', (d) => `translate(${d.x + 50},${d.y + 50})`)

      node.append('circle')
        .attr('r', 20)
        .attr('fill', (d: any) => d.data.nodeType === 'placeholder' ? '#ccc' : getNodeColor(d.data.nodeType))
        .attr('stroke', '#333')
        .attr('stroke-width', 2)

      node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d: any) => d.data.nodeType === 'placeholder' ? '?' : getNodeIcon(d.data.nodeType))

      node.append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', '#333')
        .text((d: any) => d.data.name)
        
      // Add tooltips
      node.append('title')
        .text((d: any) => {
          if (d.data.nodeType === 'placeholder') return 'No child nodes available'
          const details = [`Type: ${d.data.nodeType}`, `Name: ${d.data.name}`]
          if (d.data.nodeType === 'team' && d.data.memberCount !== undefined) {
            details.push(`Members: ${d.data.memberCount}`)
            details.push(`Machines: ${d.data.machineCount || 0}`)
          }
          if (d.data.nodeType === 'bridge' && d.data.machineCount !== undefined) {
            details.push(`Machines: ${d.data.machineCount}`)
          }
          return details.join('\n')
        })

    } else if (viewMode === 'radial') {
      // Radial layout
      const centerX = width / 2
      const centerY = height / 2
      const radius = Math.min(width, height) / 3

      // Group nodes by type
      const nodesByType = d3.group(nodes, d => d.nodeType)
      const types = Array.from(nodesByType.keys())
      const angleStep = (2 * Math.PI) / types.length

      // Position nodes in circles by type
      types.forEach((type, i) => {
        const angle = i * angleStep
        const typeNodes = nodesByType.get(type) || []
        const typeRadius = radius * (type === 'company' ? 0 : 1)
        
        typeNodes.forEach((node, j) => {
          const nodeAngle = angle + (j / typeNodes.length) * angleStep
          node.x = centerX + typeRadius * Math.cos(nodeAngle)
          node.y = centerY + typeRadius * Math.sin(nodeAngle)
        })
      })

      // Draw links
      g.append('g')
        .selectAll('line')
        .data(links)
        .join('line')
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)
        .attr('stroke', '#cccccc')
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', 2)

      // Draw nodes
      const node = g.append('g')
        .selectAll('g')
        .data(nodes)
        .join('g')
        .attr('transform', (d) => `translate(${d.x},${d.y})`)

      node.append('circle')
        .attr('r', 20)
        .attr('fill', (d) => getNodeColor(d.nodeType))
        .attr('stroke', '#333')
        .attr('stroke-width', 2)

      node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d) => getNodeIcon(d.nodeType))

      node.append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', '#333')
        .text((d) => d.name)
    }

    // Center and fit the visualization
    // Add a small delay for force simulation to settle
    setTimeout(() => {
      const bounds = g.node()?.getBBox()
      if (bounds && bounds.width > 0 && bounds.height > 0) {
        const fullWidth = bounds.width
        const fullHeight = bounds.height
        const midX = bounds.x + fullWidth / 2
        const midY = bounds.y + fullHeight / 2
        
        // Calculate scale to fit, with minimum scale of 0.5
        const scale = Math.max(0.5, Math.min(2, 0.9 / Math.max(fullWidth / width, fullHeight / height)))
        const translate = [width / 2 - scale * midX, height / 2 - scale * midY]

        svg.call(
          zoom.transform as any,
          d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
        )
      }
    }, viewMode === 'force' ? 1000 : 100) // Wait longer for force simulation

  }, [data, viewMode, isFullscreen, selectedEntityTypes, t])

  const toggleFullscreen = () => {
    if (!containerRef.current) return

    if (!isFullscreen) {
      containerRef.current.requestFullscreen?.()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen?.()
      setIsFullscreen(false)
    }
  }

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '50px' }}>
        <Spin size="large" tip={t('messages.loading', { ns: 'common' })} />
      </div>
    )
  }

  if (error) {
    return (
      <Alert
        message={t('messages.error', { ns: 'common' })}
        description={error instanceof Error ? error.message : t('architecture.fetchError')}
        type="error"
        showIcon
        action={
          <Button size="small" onClick={() => refetch()}>
            {t('actions.retry', { ns: 'common' })}
          </Button>
        }
      />
    )
  }

  if (!data) {
    return <Alert message={t('architecture.noData')} type="info" showIcon />
  }

  // Count nodes by type (filtered)
  const nodeCounts = {
    users: selectedEntityTypes.includes('user') ? (data.nodes.users?.length || 0) : 0,
    teams: selectedEntityTypes.includes('team') ? (data.nodes.teams?.length || 0) : 0,
    machines: selectedEntityTypes.includes('machine') ? (data.nodes.machines?.length || 0) : 0,
    regions: selectedEntityTypes.includes('region') ? (data.nodes.regions?.length || 0) : 0,
    bridges: selectedEntityTypes.includes('bridge') ? (data.nodes.bridges?.length || 0) : 0,
    repositories: selectedEntityTypes.includes('repository') ? (data.nodes.repositories?.length || 0) : 0,
    schedules: selectedEntityTypes.includes('schedule') ? (data.nodes.schedules?.length || 0) : 0,
    storages: selectedEntityTypes.includes('storage') ? (data.nodes.storages?.length || 0) : 0,
  }

  return (
    <div data-testid="architecture-page">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Header */}
        <Card>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Title level={4} style={{ margin: 0 }}>
                {t('architecture.title')}
              </Title>
              <Space>
                <Radio.Group 
                  value={viewMode} 
                  onChange={(e) => setViewMode(e.target.value)}
                  data-testid="architecture-view-mode-selector"
                >
                  <Radio.Button value="hierarchy" data-testid="architecture-view-hierarchy">{t('architecture.viewHierarchy')}</Radio.Button>
                  <Radio.Button value="force" data-testid="architecture-view-force">{t('architecture.viewForce')}</Radio.Button>
                  <Radio.Button value="radial" data-testid="architecture-view-radial">{t('architecture.viewRadial')}</Radio.Button>
                </Radio.Group>
                <Tooltip title={t('actions.refresh', { ns: 'common' })}>
                  <Button 
                    icon={<ReloadOutlined />} 
                    onClick={() => refetch()}
                    data-testid="architecture-refresh-button"
                  />
                </Tooltip>
                <Tooltip title={isFullscreen ? t('actions.exitFullscreen', { ns: 'common' }) : t('actions.fullscreen', { ns: 'common' })}>
                  <Button 
                    icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                    onClick={toggleFullscreen}
                    data-testid="architecture-fullscreen-button"
                  />
                </Tooltip>
              </Space>
            </div>

            {/* Filter Controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <Space align="center">
                <FilterOutlined style={{ color: '#556b2f' }} />
                <Text strong>{t('architecture.filterEntities', { ns: 'system' })}</Text>
              </Space>
              <Select
                mode="multiple"
                allowClear
                placeholder={t('architecture.selectEntities', { ns: 'system' })}
                value={selectedEntityTypes}
                onChange={setSelectedEntityTypes}
                style={{ minWidth: 400 }}
                maxTagCount={3}
                maxTagPlaceholder={(omittedValues) => `+${omittedValues.length} more`}
                data-testid="architecture-entity-filter"
              >
                {entityTypes.map(type => (
                  <Select.Option key={type.value} value={type.value} data-testid={`architecture-filter-${type.value}`}>
                    <Space>
                      <span>{type.icon}</span>
                      <span>{type.label}</span>
                    </Space>
                  </Select.Option>
                ))}
              </Select>
              <Space>
                <Button 
                  size="small"
                  onClick={() => setSelectedEntityTypes(entityTypes.map(t => t.value))}
                  data-testid="architecture-select-all-button"
                >
                  {t('architecture.selectAll', { ns: 'system' })}
                </Button>
                <Button 
                  size="small"
                  onClick={() => setSelectedEntityTypes([])}
                  data-testid="architecture-clear-all-button"
                >
                  {t('architecture.clearAll', { ns: 'system' })}
                </Button>
              </Space>
            </div>

            {/* Summary Stats */}
            <Row gutter={16}>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.users')}
                  value={nodeCounts.users}
                  prefix={<UserOutlined />}
                />
              </Col>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.teams')}
                  value={nodeCounts.teams}
                  prefix={<TeamOutlined />}
                />
              </Col>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.machines')}
                  value={nodeCounts.machines}
                  prefix={<CloudOutlined />}
                />
              </Col>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.regions')}
                  value={nodeCounts.regions}
                  prefix={<GlobalOutlined />}
                />
              </Col>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.bridges')}
                  value={nodeCounts.bridges}
                  prefix={<ApiOutlined />}
                />
              </Col>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.repositories')}
                  value={nodeCounts.repositories}
                  prefix={<InboxOutlined />}
                />
              </Col>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.schedules')}
                  value={nodeCounts.schedules}
                  prefix={<ScheduleOutlined />}
                />
              </Col>
              <Col span={3}>
                <Statistic 
                  title={t('architecture.storages')}
                  value={nodeCounts.storages}
                  prefix={<CloudOutlined />}
                />
              </Col>
            </Row>
          </Space>
        </Card>

        {/* Visualization */}
        <Card>
          <div ref={containerRef} style={{ width: '100%', height: '600px', overflow: 'hidden' }} data-testid="architecture-visualization-container">
            <svg ref={svgRef} style={{ width: '100%', height: '100%' }} data-testid="architecture-svg"></svg>
          </div>
        </Card>

        {/* Legend */}
        <Card title={t('architecture.legend')}>
          <Row gutter={[16, 16]}>
            {Object.entries({
              company: t('architecture.nodeCompany'),
              user: t('architecture.nodeUser'),
              team: t('architecture.nodeTeam'),
              region: t('architecture.nodeRegion'),
              bridge: t('architecture.nodeBridge'),
              machine: t('architecture.nodeMachine'),
              repository: t('architecture.nodeRepository'),
              schedule: t('architecture.nodeSchedule'),
              storage: t('architecture.nodeStorage'),
            }).map(([type, label]) => (
              <Col span={6} key={type} data-testid={`architecture-legend-${type}`}>
                <Space>
                  <div
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: '50%',
                      backgroundColor: getNodeColor(type),
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '12px',
                    }}
                  >
                    {getNodeIcon(type)}
                  </div>
                  <Text>{label}</Text>
                </Space>
              </Col>
            ))}
          </Row>
        </Card>
      </Space>
    </div>
  )
}

export default ArchitecturePage