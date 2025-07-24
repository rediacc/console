import React, { useEffect, useRef } from 'react'
import { MachineVaultStatusPanel } from './MachineVaultStatusPanel'
import { RepositoryDetailPanel } from './RepositoryDetailPanel'
import { Machine, Repository } from '@/types'
import { useTheme } from '@/context/ThemeContext'

interface UnifiedDetailPanelProps {
  type: 'machine' | 'repository'
  data: Machine | Repository | null
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
  // Determine actual type based on data if not explicitly provided
  const actualType = type || (data && 'machineName' in data ? 'machine' : 'repository')
  const { theme } = useTheme()
  const isDragging = useRef(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

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
      const newWidth = Math.max(300, Math.min(800, dragStartWidth.current + deltaX))
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

  if (!visible || !data) return null

  return (
    <div
      style={{
        position: 'relative',
        width: splitWidth,
        height: '100%',
        borderLeft: `1px solid ${theme === 'dark' ? '#303030' : '#f0f0f0'}`,
        display: 'flex',
        flexShrink: 0,
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
            machine={data as Machine}
            visible={visible}
            onClose={onClose}
            splitView={true}
          />
        ) : (
          <RepositoryDetailPanel
            repository={data as Repository}
            visible={visible}
            onClose={onClose}
            splitView={true}
          />
        )}
      </div>
    </div>
  )
}