import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Alert, Space, Typography, Radio, Tooltip, Statistic, Row, Col, Select } from 'antd'
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
  FilterOutlined,
  CheckOutlined,
  MinusCircleOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useCompanyArchitecture } from '@/api/queries/architecture'
import { useTheme } from '@/context/ThemeContext'
import * as d3 from 'd3'
import { SectionCard, IconButton, CompactIconButton } from '@/styles/primitives'
import { getArchitecturePalette } from './architectureTheme'
import LoadingWrapper from '@/components/common/LoadingWrapper'
import type { CompanyDataGraph, CompanyGraphNode, CompanyGraphRelationship } from '@rediacc/shared/types'
import {
  PageWrapper,
  ContentStack,
  HeaderStack,
  HeaderRow,
  ActionGroup,
  FiltersRow,
  FilterLabel,
  FilterSelectWrapper,
  FilterActions,
  VisualizationContainer,
  LoadingOverlay,
  LoadingMessage,
  VisualizationCanvas,
  LegendGrid,
  LegendItem,
  LegendIcon,
  SectionTitleText,
  CenteredState,
  CenteredMessage,
} from './styles'

const { Text } = Typography

interface GraphNode extends CompanyGraphNode, d3.SimulationNodeDatum {
  memberCount?: number
  machineCount?: number
  queueCount?: number
  regionName?: string
  parentTeam?: string
  parentRegion?: string
  parentBridge?: string
  parentStorage?: string
  children?: GraphNode[]
}

interface GraphLink extends CompanyGraphRelationship, d3.SimulationLinkDatum<GraphNode> {
  source: GraphNode
  target: GraphNode
}

type HierarchyGraphNode = GraphNode & { children?: HierarchyGraphNode[] }

const ArchitecturePage: React.FC = () => {
  const { t } = useTranslation('system')
  const { data, isLoading, error, refetch } = useCompanyArchitecture()
  const [viewMode, setViewMode] = useState<'hierarchy' | 'force' | 'radial'>('hierarchy')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [selectedEntityTypes, setSelectedEntityTypes] = useState<string[]>([
    'company', 'user', 'team', 'region', 'bridge', 'machine', 'repo', 'storage'
  ])
  const [isVisualizationLoading, setIsVisualizationLoading] = useState(false)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const { theme } = useTheme()
  const architecturePalette = useMemo(() => getArchitecturePalette(theme), [theme])

  // Available entity types for filtering
  const entityTypes = [
    { value: 'company', label: t('architecture.nodeCompany'), icon: '🏢' },
    { value: 'user', label: t('architecture.nodeUser'), icon: '👤' },
    { value: 'team', label: t('architecture.nodeTeam'), icon: '👥' },
    { value: 'region', label: t('architecture.nodeRegion'), icon: '🌍' },
    { value: 'bridge', label: t('architecture.nodeBridge'), icon: '🌉' },
    { value: 'machine', label: t('architecture.nodeMachine'), icon: '💻' },
    { value: 'repo', label: t('architecture.nodeRepo'), icon: '📦' },
    { value: 'storage', label: t('architecture.nodeStorage'), icon: '💾' },
  ]

  // Convert the nested node structure to a flat array with filtering
  const flattenNodes = (nodes: CompanyDataGraph['nodes'], filterTypes: string[]): GraphNode[] => {
    const flatNodes: GraphNode[] = []
    
    // Process each node type
    Object.entries(nodes).forEach(([type, nodeArray]) => {
      if (Array.isArray(nodeArray) && nodeArray.length > 0) {
        nodeArray.forEach((node) => {
          // Ensure nodeType is set correctly - some nodes already have it
          const nodeType = node.nodeType || type.slice(0, -1) // Use existing nodeType or derive from key
          
          // Only include if the node type is in the filter
          if (filterTypes.includes(nodeType)) {
            const nodeWithType: GraphNode = {
              ...(node as GraphNode),
              nodeType,
            }
            flatNodes.push(nodeWithType)
          }
        })
      }
    })
    
    return flatNodes
  }

  const toHierarchyNode = (node: GraphNode): HierarchyGraphNode => ({
    ...node,
  })

  // Convert relationships to links
  const flattenRelationships = (
    relationships: CompanyDataGraph['relationships'],
    nodes: GraphNode[]
  ): GraphLink[] => {
    const links: GraphLink[] = []
    const nodeMap = new Map(nodes.map(n => [n.nodeId, n]))
    
    // Process each relationship type
    Object.entries(relationships).forEach(([, relArray]) => {
      if (Array.isArray(relArray)) {
        relArray.forEach((rel) => {
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
      repo: '📁',
      storage: '☁️',
    }
    return icons[nodeType] || '📌'
  }

  // Get color for node type
  const getNodeColor = useCallback(
    (nodeType: string) => architecturePalette.nodes[nodeType] || architecturePalette.nodeFallback,
    [architecturePalette],
  )

  // Render D3 visualization
  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return
    
    setIsVisualizationLoading(true)

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
        .style('fill', architecturePalette.labelFill)
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
      .attr('fill', architecturePalette.linkStroke)

    if (viewMode === 'force') {
      // Force-directed layout
      
      // Initialize node positions
      nodes.forEach((d) => {
        d.x = width / 2 + (Math.random() - 0.5) * 100
        d.y = height / 2 + (Math.random() - 0.5) * 100
      })
      
      const simulationLinks = links.map(link => ({ ...link }))
      
      const linkForce = d3.forceLink<GraphNode, GraphLink>(simulationLinks)
        .id((d) => d.nodeId)
        .distance(150)

      const simulation = d3.forceSimulation<GraphNode>(nodes)
        .force('link', linkForce)
        .force('charge', d3.forceManyBody().strength(-500))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(40))
        .force('x', d3.forceX(width / 2).strength(0.1))
        .force('y', d3.forceY(height / 2).strength(0.1))

      // Create links
      const link = g.append('g')
        .selectAll<SVGLineElement, GraphLink>('line')
        .data(simulationLinks)
        .join('line')
        .attr('stroke', architecturePalette.linkStroke)
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', 2)
        .attr('marker-end', 'url(#arrowhead)')

      // Create nodes
      const node = g.append('g')
        .selectAll<SVGGElement, GraphNode>('g')
        .data(nodes)
        .join('g')

      node.call(d3.drag<SVGGElement, GraphNode>()
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
        .attr('stroke', architecturePalette.nodeBorder)
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .style('transition', 'all 0.2s ease')
        .on('mouseenter', function() {
          d3.select(this)
            .attr('r', 24)
            .attr('stroke-width', 3)
            .style('filter', 'brightness(1.1)')
        })
        .on('mouseleave', function() {
          d3.select(this)
            .attr('r', 20)
            .attr('stroke-width', 2)
            .style('filter', 'none')
        })

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
        .style('fill', architecturePalette.labelFill)
        .style('font-weight', '500')
        .style('text-shadow', architecturePalette.labelShadow)
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
          .attr('x1', (d) => d.source.x ?? 0)
          .attr('y1', (d) => d.source.y ?? 0)
          .attr('x2', (d) => d.target.x ?? 0)
          .attr('y2', (d) => d.target.y ?? 0)

        node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)
      })
      
      // Run the simulation
      simulation.alpha(1).restart()

    } else if (viewMode === 'hierarchy') {
      // Hierarchical layout
      const companyNode = nodes.find(n => n.nodeType === 'company')
      if (!companyNode) return

      // Build hierarchy data structure
      const hierarchyData: HierarchyGraphNode = {
        ...companyNode,
        children: [],
      }

      // Get all node types
      const teams = nodes.filter(n => n.nodeType === 'team')
      const regions = nodes.filter(n => n.nodeType === 'region')
      const users = nodes.filter(n => n.nodeType === 'user')
      const bridges = nodes.filter(n => n.nodeType === 'bridge')
      const machines = nodes.filter(n => n.nodeType === 'machine')
      const repos = nodes.filter(n => n.nodeType === 'repo')
      const storages = nodes.filter(n => n.nodeType === 'storage')

      // Build teams branch with their related nodes
      const teamsBranch: HierarchyGraphNode[] = teams.map(team => {
        const teamChildren: HierarchyGraphNode[] = []
        
        // Add users that belong to this team based on relationships
        const teamUsers = users.filter(user => 
          links.some(link => 
            link.source === user && 
            link.target === team &&
            link.relationshipType === 'memberOf'
          )
        ).map(toHierarchyNode)
        teamChildren.push(...teamUsers)
        
        // Add machines for this team (if any)
        const teamMachines = machines
          .filter(m => m.parentTeam === team.nodeId)
          .map(toHierarchyNode)
        teamChildren.push(...teamMachines)
        
        // Add repos for this team (if any)
        const teamRepos = repos
          .filter(r => r.parentTeam === team.nodeId)
          .map(toHierarchyNode)
        teamChildren.push(...teamRepos)

        // Add storages for this team (if any)
        const teamStorages = storages
          .filter(s => s.parentTeam === team.nodeId)
          .map(toHierarchyNode)
        teamChildren.push(...teamStorages)
        
        return {
          ...team,
          children: teamChildren.length > 0 ? teamChildren : undefined,
        } as HierarchyGraphNode
      })

      // Build regions branch with bridges
      const regionsBranch: HierarchyGraphNode[] = regions.map(region => {
        const regionBridges = bridges.filter(b => b.parentRegion === region.nodeId)
        
        // For each bridge, find its machines
        const bridgesWithMachines: HierarchyGraphNode[] = regionBridges.map(bridge => ({
          ...bridge,
          children: machines
            .filter(m => m.parentBridge === bridge.nodeId)
            .map(toHierarchyNode),
        }))
        
        return {
          ...region,
          children: bridgesWithMachines.length > 0 ? bridgesWithMachines : undefined,
        } as HierarchyGraphNode
      })

      // Combine all branches
      hierarchyData.children = [...teamsBranch, ...regionsBranch]

      // If no children, add a placeholder
      if (hierarchyData.children.length === 0) {
        hierarchyData.children = [{ 
          nodeId: 'placeholder', 
          name: 'No child nodes', 
          nodeType: 'placeholder',
          label: 'placeholder',
          hierarchyLevel: 'level1'
        } as HierarchyGraphNode]
      }

      const root = d3.hierarchy<HierarchyGraphNode>(hierarchyData)
      const treeLayout = d3.tree<HierarchyGraphNode>().size([width - 100, height - 100])
      const treeData = treeLayout(root)

      const linkGenerator = d3
        .linkVertical<d3.HierarchyPointLink<HierarchyGraphNode>, d3.HierarchyPointNode<HierarchyGraphNode>>()
        .x((d) => d.x + 50)
        .y((d) => d.y + 50)

      // Draw links
      g.append('g')
        .selectAll<SVGPathElement, d3.HierarchyPointLink<HierarchyGraphNode>>('path')
        .data(treeData.links())
        .join('path')
        .attr('d', (d) => linkGenerator(d) ?? '')
        .attr('fill', 'none')
        .attr('stroke', architecturePalette.linkStroke)
        .attr('stroke-width', 2)

      // Draw nodes
      const node = g.append('g')
        .selectAll<SVGGElement, d3.HierarchyPointNode<HierarchyGraphNode>>('g')
        .data(treeData.descendants())
        .join('g')
        .attr('transform', (d) => `translate(${d.x + 50},${d.y + 50})`)

      node.append('circle')
        .attr('r', 20)
        .attr('fill', (d) =>
          d.data.nodeType === 'placeholder' ? architecturePalette.nodeFallback : getNodeColor(d.data.nodeType))
        .attr('stroke', architecturePalette.nodeBorder)
        .attr('stroke-width', 2)
        .style('cursor', (d) => d.data.nodeType === 'placeholder' ? 'default' : 'pointer')
        .style('transition', 'all 0.2s ease')
        .on('mouseenter', function(_event, d) {
          if (d.data.nodeType !== 'placeholder') {
            d3.select(this)
              .attr('r', 24)
              .attr('stroke-width', 3)
              .style('filter', 'brightness(1.1)')
          }
        })
        .on('mouseleave', function(_event, d) {
          if (d.data.nodeType !== 'placeholder') {
            d3.select(this)
              .attr('r', 20)
              .attr('stroke-width', 2)
              .style('filter', 'none')
          }
        })

      node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d) => d.data.nodeType === 'placeholder' ? '?' : getNodeIcon(d.data.nodeType))

      node.append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', architecturePalette.labelFill)
        .style('font-weight', '500')
        .style('text-shadow', architecturePalette.labelShadow)
        .text((d) => d.data.name)
        
      // Add tooltips
      node.append('title')
        .text((d) => {
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
        .selectAll<SVGLineElement, GraphLink>('line')
        .data(links)
        .join('line')
        .attr('x1', (d) => d.source.x ?? 0)
        .attr('y1', (d) => d.source.y ?? 0)
        .attr('x2', (d) => d.target.x ?? 0)
        .attr('y2', (d) => d.target.y ?? 0)
        .attr('stroke', architecturePalette.linkStroke)
        .attr('stroke-opacity', 0.6)
        .attr('stroke-width', 2)

      // Draw nodes
      const node = g.append('g')
        .selectAll<SVGGElement, GraphNode>('g')
        .data(nodes)
        .join('g')
        .attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`)

      node.append('circle')
        .attr('r', 20)
        .attr('fill', (d) => getNodeColor(d.nodeType))
        .attr('stroke', architecturePalette.nodeBorder)
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .style('transition', 'all 0.2s ease')
        .on('mouseenter', function(_event, _d) {
          d3.select(this)
            .attr('r', 24)
            .attr('stroke-width', 3)
            .style('filter', 'brightness(1.1)')
        })
        .on('mouseleave', function(_event, _d) {
          d3.select(this)
            .attr('r', 20)
            .attr('stroke-width', 2)
            .style('filter', 'none')
        })

      node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d) => getNodeIcon(d.nodeType))

      node.append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', architecturePalette.labelFill)
        .style('font-weight', '500')
        .style('text-shadow', architecturePalette.labelShadow)
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

        svg.call((selection) => {
          zoom.transform(selection, d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale))
        })
      }
    }, viewMode === 'force' ? 1000 : 100) // Wait longer for force simulation
    
    // Set loading to false after rendering is complete
    setTimeout(() => {
      setIsVisualizationLoading(false)
    }, viewMode === 'force' ? 1100 : 200)

  }, [data, viewMode, isFullscreen, selectedEntityTypes, t, architecturePalette, getNodeColor])

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
      <CenteredState>
        <LoadingWrapper loading centered minHeight={160}>
          <div />
        </LoadingWrapper>
        <CenteredMessage>{t('messages.loading', { ns: 'common' })}</CenteredMessage>
      </CenteredState>
    )
  }

  if (error) {
    return (
      <PageWrapper>
        <Alert
          message={t('messages.error', { ns: 'common' })}
          description={error instanceof Error ? error.message : t('architecture.fetchError')}
          type="error"
          showIcon
          action={
            <Tooltip title={t('actions.retry', { ns: 'common' })}>
              <CompactIconButton
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => refetch()}
                aria-label={t('actions.retry', { ns: 'common' })}
              />
            </Tooltip>
          }
        />
      </PageWrapper>
    )
  }

  if (!data) {
    return (
      <PageWrapper>
        <Alert message={t('architecture.noData')} type="info" showIcon />
      </PageWrapper>
    )
  }

  // Count nodes by type (filtered)
  const nodeCounts = {
    users: selectedEntityTypes.includes('user') ? (data.nodes.users?.length || 0) : 0,
    teams: selectedEntityTypes.includes('team') ? (data.nodes.teams?.length || 0) : 0,
    machines: selectedEntityTypes.includes('machine') ? (data.nodes.machines?.length || 0) : 0,
    regions: selectedEntityTypes.includes('region') ? (data.nodes.regions?.length || 0) : 0,
    bridges: selectedEntityTypes.includes('bridge') ? (data.nodes.bridges?.length || 0) : 0,
    repos: selectedEntityTypes.includes('repo') ? (data.nodes.repos?.length || 0) : 0,
    storages: selectedEntityTypes.includes('storage') ? (data.nodes.storages?.length || 0) : 0,
  }

  return (
    <PageWrapper data-testid="architecture-page">
      <ContentStack>
        {/* Header */}
        <SectionCard>
          <HeaderStack>
            <HeaderRow>
              <SectionTitleText level={4}>{t('architecture.title')}</SectionTitleText>
              <ActionGroup>
                <Radio.Group
                  value={viewMode}
                  onChange={(e) => setViewMode(e.target.value)}
                  data-testid="architecture-view-mode-selector"
                >
                  <Radio.Button value="hierarchy" data-testid="architecture-view-hierarchy">
                    {t('architecture.viewHierarchy')}
                  </Radio.Button>
                  <Radio.Button value="force" data-testid="architecture-view-force">
                    {t('architecture.viewForce')}
                  </Radio.Button>
                  <Radio.Button value="radial" data-testid="architecture-view-radial">
                    {t('architecture.viewRadial')}
                  </Radio.Button>
                </Radio.Group>
                <Tooltip title={t('actions.refresh', { ns: 'common' })}>
                  <IconButton
                    icon={<ReloadOutlined />}
                    onClick={() => refetch()}
                    data-testid="architecture-refresh-button"
                  />
                </Tooltip>
                <Tooltip title={isFullscreen ? t('actions.exitFullscreen', { ns: 'common' }) : t('actions.fullscreen', { ns: 'common' })}>
                  <IconButton
                    icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                    onClick={toggleFullscreen}
                    data-testid="architecture-fullscreen-button"
                  />
                </Tooltip>
              </ActionGroup>
            </HeaderRow>

            <FiltersRow>
              <FilterLabel>
                <FilterOutlined />
                <Text strong>{t('architecture.filterEntities', { ns: 'system' })}</Text>
              </FilterLabel>
              <FilterSelectWrapper>
                <Select
                  mode="multiple"
                  allowClear
                  placeholder={t('architecture.selectEntities', { ns: 'system' })}
                  value={selectedEntityTypes}
                  onChange={setSelectedEntityTypes}
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
              </FilterSelectWrapper>
              <FilterActions>
                <Tooltip title={t('architecture.selectAll', { ns: 'system' })}>
                  <CompactIconButton
                    icon={<CheckOutlined />}
                    size="small"
                    onClick={() => setSelectedEntityTypes(entityTypes.map(t => t.value))}
                    data-testid="architecture-select-all-button"
                    aria-label={t('architecture.selectAll', { ns: 'system' })}
                  />
                </Tooltip>
                <Tooltip title={t('architecture.clearAll', { ns: 'system' })}>
                  <CompactIconButton
                    icon={<MinusCircleOutlined />}
                    size="small"
                    onClick={() => setSelectedEntityTypes([])}
                    data-testid="architecture-clear-all-button"
                    aria-label={t('architecture.clearAll', { ns: 'system' })}
                  />
                </Tooltip>
              </FilterActions>
            </FiltersRow>

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
                  title={t('architecture.repos')}
                  value={nodeCounts.repos}
                  prefix={<InboxOutlined />}
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
          </HeaderStack>
        </SectionCard>

        {/* Visualization */}
        <SectionCard>
          <VisualizationContainer ref={containerRef} data-testid="architecture-visualization-container">
            {isVisualizationLoading && (
              <LoadingOverlay>
                <LoadingWrapper loading centered minHeight={160}>
                  <div />
                </LoadingWrapper>
                <LoadingMessage>{t('messages.loading', { ns: 'common' })}</LoadingMessage>
              </LoadingOverlay>
            )}
            <VisualizationCanvas ref={svgRef} data-testid="architecture-svg" />
          </VisualizationContainer>
        </SectionCard>

        {/* Legend */}
        <SectionCard title={t('architecture.legend')}>
          <LegendGrid>
            {Object.entries({
              company: t('architecture.nodeCompany'),
              user: t('architecture.nodeUser'),
              team: t('architecture.nodeTeam'),
              region: t('architecture.nodeRegion'),
              bridge: t('architecture.nodeBridge'),
              machine: t('architecture.nodeMachine'),
              repo: t('architecture.nodeRepo'),
              storage: t('architecture.nodeStorage'),
            }).map(([type, label]) => (
              <LegendItem key={type} data-testid={`architecture-legend-${type}`}>
                <LegendIcon $color={getNodeColor(type)}>
                  {getNodeIcon(type)}
                </LegendIcon>
                <Text>{label}</Text>
              </LegendItem>
            ))}
          </LegendGrid>
        </SectionCard>
      </ContentStack>
    </PageWrapper>
  )
}

export default ArchitecturePage
