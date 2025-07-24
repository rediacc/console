import React, { useEffect, useRef, useState } from 'react'
import { MachineVaultStatusPanel } from './MachineVaultStatusPanel'
import { RepositoryDetailPanel } from './RepositoryDetailPanel'
import { ContainerDetailPanel } from './ContainerDetailPanel'
import { Machine, Repository } from '@/types'
import { useTheme } from '@/context/ThemeContext'

interface ContainerData {
  id: string
  name: string
  image: string
  command: string
  created: string
  status: string
  state: string
  ports: string
  port_mappings?: Array<{
    host?: string
    host_port?: string
    container_port: string
    protocol: string
  }>
  labels: string
  mounts: string
  networks: string
  size: string
  repository: string
  cpu_percent: string
  memory_usage: string
  memory_percent: string
  net_io: string
  block_io: string
  pids: string
}

interface UnifiedDetailPanelProps {
  type: 'machine' | 'repository' | 'container'
  data: Machine | Repository | ContainerData | null
  visible: boolean
  onClose: () => void
  splitWidth: number
  onSplitWidthChange: (width: number) => void
}

export const UnifiedDetailPanel: React.FC<UnifiedDetailPanelProps> = ({
  type,
  data,
  visible,
  onClose,
  splitWidth,
  onSplitWidthChange
}) => {
  const { theme } = useTheme()
  const isDragging = useRef(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)
  
  // State for fade transition
  const [opacity, setOpacity] = useState(1)
  const [currentData, setCurrentData] = useState(data)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const prevDataRef = useRef(data)

  // Handle data changes with fade transition
  useEffect(() => {
    // Check if data has actually changed (different entity)
    if (!data || !prevDataRef.current) {
      setCurrentData(data)
      setOpacity(1)
      prevDataRef.current = data
      return
    }

    const prevId = 'machineName' in prevDataRef.current ? prevDataRef.current.machineName :
                   'repositoryName' in prevDataRef.current ? prevDataRef.current.repositoryName :
                   'id' in prevDataRef.current ? prevDataRef.current.id : null

    const currentId = 'machineName' in data ? data.machineName :
                      'repositoryName' in data ? data.repositoryName :
                      'id' in data ? data.id : null

    if (prevId !== currentId) {
      // Data has changed, trigger fade transition
      setIsTransitioning(true)
      setOpacity(0)

      // After fade out, switch data
      setTimeout(() => {
        setCurrentData(data)
        // Fade in new content
        setTimeout(() => {
          setOpacity(1)
          setTimeout(() => {
            setIsTransitioning(false)
          }, 300)
        }, 50)
      }, 300)

      prevDataRef.current = data
    } else {
      // Same entity, just update without transition
      setCurrentData(data)
      prevDataRef.current = data
    }
  }, [data])

  // Handle resize
  const handleMouseDown = (e: React.MouseEvent) => {
    isDragging.current = true
    dragStartX.current = e.clientX
    dragStartWidth.current = splitWidth
    document.body.style.cursor = 'ew-resize'
    document.body.style.userSelect = 'none'
    e.preventDefault()
  }

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return

      const deltaX = dragStartX.current - e.clientX
      const windowWidth = window.innerWidth
      const maxWidth = Math.min(800, windowWidth - 400) // Leave at least 400px for the table
      const newWidth = Math.max(300, Math.min(maxWidth, dragStartWidth.current + deltaX))
      onSplitWidthChange(newWidth)
    }

    const handleMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [splitWidth, onSplitWidthChange])

  if (!visible || !currentData) return null

  // Determine actual type based on currentData if not explicitly provided
  const actualType = type || (currentData && 'machineName' in currentData ? 'machine' : 
                             currentData && 'repositoryName' in currentData ? 'repository' : 'container')

  return (
    <div
      style={{
        position: 'relative',
        width: splitWidth,
        height: '100%',
        borderLeft: `1px solid ${theme === 'dark' ? '#303030' : '#f0f0f0'}`,
        display: 'flex',
        flexShrink: 0,
        opacity,
        transition: 'opacity 0.3s ease',
      }}
    >
      {/* Resize Handle */}
      <div
        style={{
          position: 'absolute',
          left: -3,
          top: 0,
          bottom: 0,
          width: 6,
          cursor: 'ew-resize',
          zIndex: 10,
          backgroundColor: 'transparent',
        }}
        onMouseDown={handleMouseDown}
      >
        <div
          style={{
            position: 'absolute',
            left: 2,
            top: 0,
            bottom: 0,
            width: 2,
            backgroundColor: theme === 'dark' ? '#303030' : '#f0f0f0',
            transition: 'background-color 0.2s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = '#1890ff'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = theme === 'dark' ? '#303030' : '#f0f0f0'
          }}
        />
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {actualType === 'machine' ? (
          <MachineVaultStatusPanel
            machine={currentData as Machine}
            visible={visible}
            onClose={onClose}
            splitView={true}
          />
        ) : actualType === 'repository' ? (
          <RepositoryDetailPanel
            repository={currentData as Repository}
            visible={visible}
            onClose={onClose}
            splitView={true}
          />
        ) : (
          <ContainerDetailPanel
            container={currentData as ContainerData}
            visible={visible}
            onClose={onClose}
            splitView={true}
          />
        )}
      </div>
    </div>
  )
}