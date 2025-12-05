export type ArchitectureMode = 'light' | 'dark'

type NodeColorMap = Record<string, string>

const NODE_COLORS: Record<ArchitectureMode, NodeColorMap> = {
  light: {
    company: '#e0e0e0',
    user: '#d6d6d6',
    team: '#cccccc',
    region: '#c2c2c2',
    bridge: '#b8b8b8',
    machine: '#aeaeae',
    repo: '#a4a4a4',
    storage: '#909090',
  },
  dark: {
    company: '#4a5568',
    user: '#5a6778',
    team: '#6a7788',
    region: '#7a8798',
    bridge: '#8a97a8',
    machine: '#9aa7b8',
    repo: '#aab7c8',
    storage: '#cad7e8',
  },
}

export interface ArchitecturePalette {
  nodes: NodeColorMap
  nodeFallback: string
  nodeBorder: string
  linkStroke: string
  labelFill: string
  labelShadow: string
}

const architecturePalette: Record<ArchitectureMode, ArchitecturePalette> = {
  light: {
    nodes: NODE_COLORS.light,
    nodeFallback: '#cccccc',
    nodeBorder: '#333333',
    linkStroke: '#cccccc',
    labelFill: '#1a1a1a',
    labelShadow: '1px 1px 2px rgba(255,255,255,0.8)',
  },
  dark: {
    nodes: NODE_COLORS.dark,
    nodeFallback: '#6a7788',
    nodeBorder: '#333333',
    linkStroke: '#cccccc',
    labelFill: '#e8e8e8',
    labelShadow: '1px 1px 2px rgba(0,0,0,0.8)',
  },
}

export const getArchitecturePalette = (mode: ArchitectureMode): ArchitecturePalette =>
  architecturePalette[mode] || architecturePalette.light
