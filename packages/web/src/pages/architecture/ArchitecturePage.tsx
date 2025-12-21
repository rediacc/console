import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Flex,
  Radio,
  Row,
  Select,
  Space,
  Statistic,
  Tooltip,
  Typography,
  theme as antdTheme,
} from 'antd';
import * as d3 from 'd3';
import { useTranslation } from 'react-i18next';
import { useCompanyArchitecture } from '@/api/queries/architecture';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { useTheme } from '@/context/ThemeContext';
import {
  ApiOutlined,
  CheckOutlined,
  CloudOutlined,
  FilterOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  GlobalOutlined,
  InboxOutlined,
  MinusCircleOutlined,
  ReloadOutlined,
  TeamOutlined,
  UserOutlined,
} from '@/utils/optimizedIcons';
import type { CompanyDataGraph, CompanyGraphNode } from '@rediacc/shared/types';
import { getArchitecturePalette } from './architectureTheme';

interface GraphNode extends CompanyGraphNode, d3.SimulationNodeDatum {
  memberCount?: number;
  machineCount?: number;
  queueCount?: number;
  regionName?: string;
  parentTeam?: string;
  parentRegion?: string;
  parentBridge?: string;
  parentStorage?: string;
  children?: GraphNode[];
}

interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
  source: GraphNode;
  target: GraphNode;
  relationshipType: string;
  label: string;
}

type HierarchyGraphNode = GraphNode & { children?: HierarchyGraphNode[] };

const ArchitecturePage: React.FC = () => {
  const { t } = useTranslation('system');
  const { data, isLoading, error, refetch } = useCompanyArchitecture();
  const [viewMode, setViewMode] = useState<'hierarchy' | 'force' | 'radial'>('hierarchy');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedEntityTypes, setSelectedEntityTypes] = useState<string[]>([
    'company',
    'user',
    'team',
    'region',
    'bridge',
    'machine',
    'repository',
    'storage',
  ]);
  const [isVisualizationLoading, setIsVisualizationLoading] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { theme } = useTheme();
  const { token } = antdTheme.useToken();
  const borderColor = token.colorBorderSecondary ?? token.colorBorder;
  const architecturePalette = useMemo(() => getArchitecturePalette(theme), [theme]);

  // Available entity types for filtering
  const entityTypes = [
    { value: 'company', label: t('architecture.nodeCompany'), icon: '🏢' },
    { value: 'user', label: t('architecture.nodeUser'), icon: '👤' },
    { value: 'team', label: t('architecture.nodeTeam'), icon: '👥' },
    { value: 'region', label: t('architecture.nodeRegion'), icon: '🌍' },
    { value: 'bridge', label: t('architecture.nodeBridge'), icon: '🌉' },
    { value: 'machine', label: t('architecture.nodeMachine'), icon: '💻' },
    { value: 'repository', label: t('architecture.nodeRepository'), icon: '📦' },
    { value: 'storage', label: t('architecture.nodeStorage'), icon: '💾' },
  ];

  // Convert the nested node structure to a flat array with filtering
  const flattenNodes = (nodes: CompanyDataGraph['nodes'], filterTypes: string[]): GraphNode[] => {
    const flatNodes: GraphNode[] = [];

    // Process each node type
    Object.entries(nodes).forEach(([type, nodeArray]) => {
      if (Array.isArray(nodeArray) && nodeArray.length > 0) {
        nodeArray.forEach((node) => {
          // Ensure nodeType is set correctly - some nodes already have it
          const nodeType = node.nodeType || type.slice(0, -1); // Use existing nodeType or derive from key

          // Only include if the node type is in the filter
          if (filterTypes.includes(nodeType)) {
            const nodeWithType: GraphNode = {
              ...(node as GraphNode),
              nodeType,
            };
            flatNodes.push(nodeWithType);
          }
        });
      }
    });

    return flatNodes;
  };

  const toHierarchyNode = (node: GraphNode): HierarchyGraphNode => ({
    ...node,
  });

  // Convert relationships to links
  const flattenRelationships = (
    relationships: CompanyDataGraph['relationships'],
    nodes: GraphNode[]
  ): GraphLink[] => {
    const links: GraphLink[] = [];
    const nodeMap = new Map(nodes.map((n) => [n.nodeId, n]));

    // Process each relationship type
    Object.entries(relationships).forEach(([, relArray]) => {
      if (Array.isArray(relArray)) {
        relArray.forEach((rel) => {
          const source = nodeMap.get(rel.source);
          const target = nodeMap.get(rel.target);
          if (source && target) {
            links.push({
              source,
              target,
              relationshipType: rel.relationshipType,
              label: rel.label,
            });
          }
        });
      }
    });

    return links;
  };

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
      storage: '☁️',
    };
    return icons[nodeType] || '📌';
  };

  // Get color for node type
  const getNodeColor = useCallback(
    (nodeType: string) => architecturePalette.nodes[nodeType] || architecturePalette.nodeFallback,
    [architecturePalette]
  );

  // Render D3 visualization
  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return;

    setIsVisualizationLoading(true);

    const width = containerRef.current.clientWidth || 800;
    const height = 600;

    const nodes = flattenNodes(data.nodes, selectedEntityTypes);
    const links = flattenRelationships(data.relationships, nodes);

    // Check if we have nodes
    if (nodes.length === 0) {
      // Clear the svg and show empty state
      d3.select(svgRef.current).selectAll('*').remove();

      const svg = d3.select(svgRef.current).attr('width', width).attr('height', height);

      svg
        .append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .style('fill', architecturePalette.labelFill)
        .text(t('architecture.noEntitiesSelected', { ns: 'system' }));

      return;
    }

    // Clear previous visualization
    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current).attr('width', width).attr('height', height);

    // Add zoom behavior
    const g = svg.append('g').attr('class', 'main-group');

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);

    // Create arrow markers for directed edges
    const defs = svg.append('defs');
    defs
      .append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 20)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('path')
      .attr('d', 'M 0,-5 L 10,0 L 0,5')
      .attr('fill', architecturePalette.linkStroke);

    if (viewMode === 'force') {
      // Force-directed layout

      // Initialize node positions
      nodes.forEach((d) => {
        d.x = width / 2 + (Math.random() - 0.5) * 100;
        d.y = height / 2 + (Math.random() - 0.5) * 100;
      });

      const simulationLinks = links.map((link) => ({ ...link }));

      const linkForce = d3
        .forceLink<GraphNode, GraphLink>(simulationLinks)
        .id((d) => d.nodeId)
        .distance(150);

      const simulation = d3
        .forceSimulation<GraphNode>(nodes)
        .force('link', linkForce)
        .force('charge', d3.forceManyBody().strength(-500))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(40))
        .force('x', d3.forceX(width / 2).strength(0.1))
        .force('y', d3.forceY(height / 2).strength(0.1));

      // Create links
      const link = g
        .append('g')
        .selectAll<SVGLineElement, GraphLink>('line')
        .data(simulationLinks)
        .join('line')
        .attr('stroke', borderColor)
        .attr('stroke-width', 2)
        .attr('marker-end', 'url(#arrowhead)');

      // Create nodes
      const node = g.append('g').selectAll<SVGGElement, GraphNode>('g').data(nodes).join('g');

      node.call(
        d3
          .drag<SVGGElement, GraphNode>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

      // Add circles for nodes
      node
        .append('circle')
        .attr('r', 20)
        .attr('fill', (d) => getNodeColor(d.nodeType))
        .attr('stroke', architecturePalette.nodeBorder)
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .style('transition', 'all 0.2s ease')
        .on('mouseenter', function () {
          d3.select(this).attr('r', 24).attr('stroke-width', 3).style('filter', 'brightness(1.1)');
        })
        .on('mouseleave', function () {
          d3.select(this).attr('r', 20).attr('stroke-width', 2).style('filter', 'none');
        });

      // Add icons
      node
        .append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d) => getNodeIcon(d.nodeType));

      // Add labels
      node
        .append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', architecturePalette.labelFill)
        .style('font-weight', '500')
        .text((d) => d.name);

      // Add tooltips
      node.append('title').text((d) => {
        const details = [`Type: ${d.nodeType}`, `Name: ${d.name}`];
        if (d.nodeType === 'team' && d.memberCount !== undefined) {
          details.push(`Members: ${d.memberCount}`);
          details.push(`Machines: ${d.machineCount || 0}`);
        }
        if (d.nodeType === 'machine' && d.queueCount !== undefined) {
          details.push(`Queue Items: ${d.queueCount}`);
          details.push(`Region: ${d.regionName}`);
        }
        return details.join('\n');
      });

      simulation.on('tick', () => {
        link
          .attr('x1', (d) => d.source.x ?? 0)
          .attr('y1', (d) => d.source.y ?? 0)
          .attr('x2', (d) => d.target.x ?? 0)
          .attr('y2', (d) => d.target.y ?? 0);

        node.attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
      });

      // Run the simulation
      simulation.alpha(1).restart();
    } else if (viewMode === 'hierarchy') {
      // Hierarchical layout
      const companyNode = nodes.find((n) => n.nodeType === 'company');
      if (!companyNode) return;

      // Build hierarchy data structure
      const hierarchyData: HierarchyGraphNode = {
        ...companyNode,
        children: [],
      };

      // Get all node types
      const teams = nodes.filter((n) => n.nodeType === 'team');
      const regions = nodes.filter((n) => n.nodeType === 'region');
      const users = nodes.filter((n) => n.nodeType === 'user');
      const bridges = nodes.filter((n) => n.nodeType === 'bridge');
      const machines = nodes.filter((n) => n.nodeType === 'machine');
      const repositories = nodes.filter((n) => n.nodeType === 'repository');
      const storages = nodes.filter((n) => n.nodeType === 'storage');

      // Build teams branch with their related nodes
      const teamsBranch: HierarchyGraphNode[] = teams.map((team) => {
        const teamChildren: HierarchyGraphNode[] = [];

        // Add users that belong to this team based on relationships
        const teamUsers = users
          .filter((user) =>
            links.some(
              (link) =>
                link.source === user && link.target === team && link.relationshipType === 'memberOf'
            )
          )
          .map(toHierarchyNode);
        teamChildren.push(...teamUsers);

        // Add machines for this team (if any)
        const teamMachines = machines
          .filter((m) => m.parentTeam === team.nodeId)
          .map(toHierarchyNode);
        teamChildren.push(...teamMachines);

        // Add repositories for this team (if any)
        const teamRepositories = repositories
          .filter((r) => r.parentTeam === team.nodeId)
          .map(toHierarchyNode);
        teamChildren.push(...teamRepositories);

        // Add storages for this team (if any)
        const teamStorages = storages
          .filter((s) => s.parentTeam === team.nodeId)
          .map(toHierarchyNode);
        teamChildren.push(...teamStorages);

        return {
          ...team,
          children: teamChildren.length > 0 ? teamChildren : undefined,
        } as HierarchyGraphNode;
      });

      // Build regions branch with bridges
      const regionsBranch: HierarchyGraphNode[] = regions.map((region) => {
        const regionBridges = bridges.filter((b) => b.parentRegion === region.nodeId);

        // For each bridge, find its machines
        const bridgesWithMachines: HierarchyGraphNode[] = regionBridges.map((bridge) => ({
          ...bridge,
          children: machines.filter((m) => m.parentBridge === bridge.nodeId).map(toHierarchyNode),
        }));

        return {
          ...region,
          children: bridgesWithMachines.length > 0 ? bridgesWithMachines : undefined,
        } as HierarchyGraphNode;
      });

      // Combine all branches
      hierarchyData.children = [...teamsBranch, ...regionsBranch];

      // If no children, add a placeholder
      if (hierarchyData.children.length === 0) {
        hierarchyData.children = [
          {
            nodeId: 'placeholder',
            name: 'No child nodes',
            nodeType: 'placeholder',
            label: 'placeholder',
            hierarchyLevel: 'level1',
          } as HierarchyGraphNode,
        ];
      }

      const root = d3.hierarchy<HierarchyGraphNode>(hierarchyData);
      const treeLayout = d3.tree<HierarchyGraphNode>().size([width - 100, height - 100]);
      const treeData = treeLayout(root);

      const linkGenerator = d3
        .linkVertical<
          d3.HierarchyPointLink<HierarchyGraphNode>,
          d3.HierarchyPointNode<HierarchyGraphNode>
        >()
        .x((d) => d.x + 50)
        .y((d) => d.y + 50);

      // Draw links
      g.append('g')
        .selectAll<SVGPathElement, d3.HierarchyPointLink<HierarchyGraphNode>>('path')
        .data(treeData.links())
        .join('path')
        .attr('d', (d) => linkGenerator(d) ?? '')
        .attr('fill', 'none')
        .attr('stroke', architecturePalette.linkStroke)
        .attr('stroke-width', 2);

      // Draw nodes
      const node = g
        .append('g')
        .selectAll<SVGGElement, d3.HierarchyPointNode<HierarchyGraphNode>>('g')
        .data(treeData.descendants())
        .join('g')
        .attr('transform', (d) => `translate(${d.x + 50},${d.y + 50})`);

      node
        .append('circle')
        .attr('r', 20)
        .attr('fill', (d) =>
          d.data.nodeType === 'placeholder'
            ? architecturePalette.nodeFallback
            : getNodeColor(d.data.nodeType)
        )
        .attr('stroke', architecturePalette.nodeBorder)
        .attr('stroke-width', 2)
        .style('cursor', (d) => (d.data.nodeType === 'placeholder' ? 'default' : 'pointer'))
        .style('transition', 'all 0.2s ease')
        .on('mouseenter', function (_event, d) {
          if (d.data.nodeType !== 'placeholder') {
            d3.select(this)
              .attr('r', 24)
              .attr('stroke-width', 3)
              .style('filter', 'brightness(1.1)');
          }
        })
        .on('mouseleave', function (_event, d) {
          if (d.data.nodeType !== 'placeholder') {
            d3.select(this).attr('r', 20).attr('stroke-width', 2).style('filter', 'none');
          }
        });

      node
        .append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d) => (d.data.nodeType === 'placeholder' ? '?' : getNodeIcon(d.data.nodeType)));

      node
        .append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', architecturePalette.labelFill)
        .style('font-weight', '500')
        .text((d) => d.data.name);

      // Add tooltips
      node.append('title').text((d) => {
        if (d.data.nodeType === 'placeholder') return 'No child nodes available';
        const details = [`Type: ${d.data.nodeType}`, `Name: ${d.data.name}`];
        if (d.data.nodeType === 'team' && d.data.memberCount !== undefined) {
          details.push(`Members: ${d.data.memberCount}`);
          details.push(`Machines: ${d.data.machineCount || 0}`);
        }
        if (d.data.nodeType === 'bridge' && d.data.machineCount !== undefined) {
          details.push(`Machines: ${d.data.machineCount}`);
        }
        return details.join('\n');
      });
    } else if (viewMode === 'radial') {
      // Radial layout
      const centerX = width / 2;
      const centerY = height / 2;
      const radius = Math.min(width, height) / 3;

      // Group nodes by type
      const nodesByType = d3.group(nodes, (d) => d.nodeType);
      const types = Array.from(nodesByType.keys());
      const angleStep = (2 * Math.PI) / types.length;

      // Position nodes in circles by type
      types.forEach((type, i) => {
        const angle = i * angleStep;
        const typeNodes = nodesByType.get(type) || [];
        const typeRadius = radius * (type === 'company' ? 0 : 1);

        typeNodes.forEach((node, j) => {
          const nodeAngle = angle + (j / typeNodes.length) * angleStep;
          node.x = centerX + typeRadius * Math.cos(nodeAngle);
          node.y = centerY + typeRadius * Math.sin(nodeAngle);
        });
      });

      // Draw links
      g.append('g')
        .selectAll<SVGLineElement, GraphLink>('line')
        .data(links)
        .join('line')
        .attr('x1', (d) => d.source.x ?? 0)
        .attr('y1', (d) => d.source.y ?? 0)
        .attr('x2', (d) => d.target.x ?? 0)
        .attr('y2', (d) => d.target.y ?? 0)
        .attr('stroke', borderColor)
        .attr('stroke-width', 2);

      // Draw nodes
      const node = g
        .append('g')
        .selectAll<SVGGElement, GraphNode>('g')
        .data(nodes)
        .join('g')
        .attr('transform', (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);

      node
        .append('circle')
        .attr('r', 20)
        .attr('fill', (d) => getNodeColor(d.nodeType))
        .attr('stroke', architecturePalette.nodeBorder)
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .style('transition', 'all 0.2s ease')
        .on('mouseenter', function (_event, _d) {
          d3.select(this).attr('r', 24).attr('stroke-width', 3).style('filter', 'brightness(1.1)');
        })
        .on('mouseleave', function (_event, _d) {
          d3.select(this).attr('r', 20).attr('stroke-width', 2).style('filter', 'none');
        });

      node
        .append('text')
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('font-size', '16px')
        .text((d) => getNodeIcon(d.nodeType));

      node
        .append('text')
        .attr('dy', 35)
        .attr('text-anchor', 'middle')
        .style('font-size', '12px')
        .style('fill', architecturePalette.labelFill)
        .style('font-weight', '500')
        .text((d) => d.name);
    }

    // Center and fit the visualization
    // Add a small delay for force simulation to settle
    setTimeout(
      () => {
        const bounds = g.node()?.getBBox();
        if (bounds && bounds.width > 0 && bounds.height > 0) {
          const fullWidth = bounds.width;
          const fullHeight = bounds.height;
          const midX = bounds.x + fullWidth / 2;
          const midY = bounds.y + fullHeight / 2;

          // Calculate scale to fit, with minimum scale of 0.5
          const scale = Math.max(
            0.5,
            Math.min(2, 0.9 / Math.max(fullWidth / width, fullHeight / height))
          );
          const translate = [width / 2 - scale * midX, height / 2 - scale * midY];

          svg.call((selection) => {
            zoom.transform(
              selection,
              d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
            );
          });
        }
      },
      viewMode === 'force' ? 1000 : 100
    ); // Wait longer for force simulation

    // Set loading to false after rendering is complete
    setTimeout(
      () => {
        setIsVisualizationLoading(false);
      },
      viewMode === 'force' ? 1100 : 200
    );
  }, [
    data,
    viewMode,
    isFullscreen,
    selectedEntityTypes,
    t,
    architecturePalette,
    getNodeColor,
    borderColor,
  ]);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;

    if (isFullscreen) {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    } else {
      containerRef.current.requestFullscreen?.();
      setIsFullscreen(true);
    }
  };

  if (isLoading) {
    return (
      <Flex vertical align="center" style={{ width: '100%' }}>
        <LoadingWrapper loading centered minHeight={160}>
          <Flex />
        </LoadingWrapper>
        <Typography.Text>{t('messages.loading', { ns: 'common' })}</Typography.Text>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex>
        <Alert
          message={t('messages.error', { ns: 'common' })}
          description={error instanceof Error ? error.message : t('architecture.fetchError')}
          type="error"
          showIcon
          action={
            <Tooltip title={t('actions.retry', { ns: 'common' })}>
              <Button
                type="text"
                icon={<ReloadOutlined />}
                onClick={() => refetch()}
                aria-label={t('actions.retry', { ns: 'common' })}
              />
            </Tooltip>
          }
        />
      </Flex>
    );
  }

  if (!data) {
    return (
      <Flex>
        <Alert message={t('architecture.noData')} type="info" showIcon />
      </Flex>
    );
  }

  // Count nodes by type (filtered)
  const nodeCounts = {
    users: selectedEntityTypes.includes('user') ? data.nodes.users?.length || 0 : 0,
    teams: selectedEntityTypes.includes('team') ? data.nodes.teams?.length || 0 : 0,
    machines: selectedEntityTypes.includes('machine') ? data.nodes.machines?.length || 0 : 0,
    regions: selectedEntityTypes.includes('region') ? data.nodes.regions?.length || 0 : 0,
    bridges: selectedEntityTypes.includes('bridge') ? data.nodes.bridges?.length || 0 : 0,
    repositories: selectedEntityTypes.includes('repository') ? data.nodes.repos?.length || 0 : 0,
    storages: selectedEntityTypes.includes('storage') ? data.nodes.storages?.length || 0 : 0,
  };

  return (
    <Flex vertical data-testid="architecture-page">
      <Flex vertical gap={24} style={{ width: '100%' }}>
        {/* Header */}
        <Card>
          <Flex vertical gap={16} style={{ width: '100%' }}>
            <Flex align="center" justify="space-between" wrap>
              <Flex>
                <Typography.Title level={4} style={{ margin: 0 }}>
                  {t('architecture.title')}
                </Typography.Title>
              </Flex>
              <Flex align="center" wrap>
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
                  <Button
                    type="text"
                    icon={<ReloadOutlined />}
                    onClick={() => refetch()}
                    data-testid="architecture-refresh-button"
                  />
                </Tooltip>
                <Tooltip
                  title={
                    isFullscreen
                      ? t('actions.exitFullscreen', { ns: 'common' })
                      : t('actions.fullscreen', { ns: 'common' })
                  }
                >
                  <Button
                    type="text"
                    icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                    onClick={toggleFullscreen}
                    data-testid="architecture-fullscreen-button"
                  />
                </Tooltip>
              </Flex>
            </Flex>

            <Flex align="center">
              <Flex align="center" style={{ fontWeight: 500 }}>
                <FilterOutlined />
                <Typography.Text strong>
                  {t('architecture.filterEntities', { ns: 'system' })}
                </Typography.Text>
              </Flex>
              <Flex style={{ width: '100%', minWidth: 320 }}>
                <Select
                  mode="multiple"
                  allowClear
                  placeholder={t('architecture.selectEntities', { ns: 'system' })}
                  value={selectedEntityTypes}
                  onChange={setSelectedEntityTypes}
                  maxTagCount={3}
                  maxTagPlaceholder={(omittedValues) => `+${omittedValues.length} more`}
                  options={entityTypes.map((type) => ({
                    value: type.value,
                    label: (
                      <Space>
                        <Typography.Text>{type.icon}</Typography.Text>
                        <Typography.Text>{type.label}</Typography.Text>
                      </Space>
                    ),
                  }))}
                  data-testid="architecture-entity-filter"
                />
              </Flex>
              <Flex style={{ width: 'auto' }}>
                <Tooltip title={t('architecture.selectAll', { ns: 'system' })}>
                  <Button
                    type="text"
                    icon={<CheckOutlined />}
                    onClick={() => setSelectedEntityTypes(entityTypes.map((t) => t.value))}
                    data-testid="architecture-select-all-button"
                    aria-label={t('architecture.selectAll', { ns: 'system' })}
                  />
                </Tooltip>
                <Tooltip title={t('architecture.clearAll', { ns: 'system' })}>
                  <Button
                    type="text"
                    icon={<MinusCircleOutlined />}
                    onClick={() => setSelectedEntityTypes([])}
                    data-testid="architecture-clear-all-button"
                    aria-label={t('architecture.clearAll', { ns: 'system' })}
                  />
                </Tooltip>
              </Flex>
            </Flex>

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
                  title={t('architecture.storages')}
                  value={nodeCounts.storages}
                  prefix={<CloudOutlined />}
                />
              </Col>
            </Row>
          </Flex>
        </Card>

        {/* Visualization */}
        <Card>
          <Flex
            ref={containerRef}
            data-testid="architecture-visualization-container"
            style={{ width: '100%', height: 360, overflow: 'hidden', position: 'relative' }}
          >
            {isVisualizationLoading && (
              <Flex
                vertical
                align="center"
                justify="center"
                style={{
                  position: 'absolute',
                  inset: 0,
                  zIndex: 1000,
                }}
              >
                <LoadingWrapper loading centered minHeight={160}>
                  <Flex />
                </LoadingWrapper>
                <Typography.Text>{t('messages.loading', { ns: 'common' })}</Typography.Text>
              </Flex>
            )}
            <svg ref={svgRef} width="100%" height="100%" data-testid="architecture-svg" />
          </Flex>
        </Card>

        {/* Legend */}
        <Card title={t('architecture.legend')}>
          <Flex
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            }}
          >
            {Object.entries({
              company: t('architecture.nodeCompany'),
              user: t('architecture.nodeUser'),
              team: t('architecture.nodeTeam'),
              region: t('architecture.nodeRegion'),
              bridge: t('architecture.nodeBridge'),
              machine: t('architecture.nodeMachine'),
              repository: t('architecture.nodeRepository'),
              storage: t('architecture.nodeStorage'),
            }).map(([type, label]) => (
              <Flex key={type} align="center" data-testid={`architecture-legend-${type}`}>
                <Flex
                  align="center"
                  justify="center"
                  style={{
                    width: 24,
                    height: 24,
                    fontSize: 12,
                    backgroundColor: getNodeColor(type),
                  }}
                >
                  {getNodeIcon(type)}
                </Flex>
                <Typography.Text>{label}</Typography.Text>
              </Flex>
            ))}
          </Flex>
        </Card>
      </Flex>
    </Flex>
  );
};

export default ArchitecturePage;
