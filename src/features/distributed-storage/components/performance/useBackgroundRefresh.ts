import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useMachineSelection } from '@/store/distributedStorage/hooks'
import type { Machine } from '@/types'

export interface BackgroundRefreshOptions {
  interval?: number
  onlyWhenVisible?: boolean
  onlySelectedMachines?: boolean
  maxMachines?: number
  enabled?: boolean
}

export interface BackgroundRefreshState {
  isRefreshing: boolean
  lastRefresh: Date | null
  refreshCount: number
  nextRefresh: Date | null
}

/**
 * Hook for background refresh of machine statuses
 */
export const useBackgroundRefresh = (
  machines: Machine[],
  teamName: string,
  options: BackgroundRefreshOptions = {}
) => {
  const {
    interval = 30000, // 30 seconds
    onlyWhenVisible = true,
    onlySelectedMachines = false,
    maxMachines = 50,
    enabled = true
  } = options

  const queryClient = useQueryClient()
  const { selectedMachines } = useMachineSelection()
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const visibilityRef = useRef(true)
  
  const [state, setState] = useState<BackgroundRefreshState>({
    isRefreshing: false,
    lastRefresh: null,
    refreshCount: 0,
    nextRefresh: null
  })

  // Store scheduleNextRefresh in a ref to avoid dependency issues
  const scheduleNextRefreshRef = useRef<() => void>(() => {})

  // Handle visibility change
  useEffect(() => {
    if (!onlyWhenVisible) return

    const handleVisibilityChange = () => {
      visibilityRef.current = document.visibilityState === 'visible'

      // Resume refresh when becoming visible
      if (visibilityRef.current && enabled) {
        scheduleNextRefreshRef.current()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [onlyWhenVisible, enabled])

  // Calculate next refresh time
  const calculateNextRefresh = useCallback(() => {
    return new Date(Date.now() + interval)
  }, [interval])

  // Determine which machines to refresh
  const getMachinesToRefresh = useCallback(() => {
    let machinesToRefresh = machines

    // Filter by selected machines if enabled
    if (onlySelectedMachines && selectedMachines.length > 0) {
      machinesToRefresh = machines.filter(m => 
        selectedMachines.includes(m.machineName)
      )
    }

    // Limit number of machines
    if (machinesToRefresh.length > maxMachines) {
      // Prioritize selected machines, then take first N
      const selected = machinesToRefresh.filter(m => 
        selectedMachines.includes(m.machineName)
      )
      const unselected = machinesToRefresh.filter(m => 
        !selectedMachines.includes(m.machineName)
      )
      
      machinesToRefresh = [
        ...selected.slice(0, maxMachines),
        ...unselected.slice(0, Math.max(0, maxMachines - selected.length))
      ]
    }

    return machinesToRefresh
  }, [machines, selectedMachines, onlySelectedMachines, maxMachines])

  // Refresh function
  const refresh = useCallback(async () => {
    if (!enabled || (onlyWhenVisible && !visibilityRef.current)) {
      return
    }

    setState(prev => ({ ...prev, isRefreshing: true }))

    try {
      const machinesToRefresh = getMachinesToRefresh()
      
      // Invalidate queries for these machines
      await Promise.all(
        machinesToRefresh.map(machine =>
          queryClient.invalidateQueries({
            queryKey: ['machineAssignmentStatus', teamName, machine.machineName]
          })
        )
      )

      setState(prev => ({
        isRefreshing: false,
        lastRefresh: new Date(),
        refreshCount: prev.refreshCount + 1,
        nextRefresh: calculateNextRefresh()
      }))
    } catch (error) {
      console.error('Background refresh failed:', error)
      setState(prev => ({
        ...prev,
        isRefreshing: false,
        nextRefresh: calculateNextRefresh()
      }))
    }
  }, [enabled, onlyWhenVisible, getMachinesToRefresh, queryClient, teamName, calculateNextRefresh])

  // Schedule next refresh
  const scheduleNextRefresh = useCallback(() => {
    if (intervalRef.current) {
      clearTimeout(intervalRef.current)
    }

    if (!enabled) return

    setState(prev => ({ ...prev, nextRefresh: calculateNextRefresh() }))

    intervalRef.current = setTimeout(() => {
      refresh()
      scheduleNextRefreshRef.current()
    }, interval)
  }, [enabled, interval, refresh, calculateNextRefresh])

  // Update the ref whenever scheduleNextRefresh changes
  useEffect(() => {
    scheduleNextRefreshRef.current = scheduleNextRefresh
  }, [scheduleNextRefresh])

  // Manual refresh
  const manualRefresh = useCallback(async () => {
    if (intervalRef.current) {
      clearTimeout(intervalRef.current)
    }
    
    await refresh()
    
    if (enabled) {
      scheduleNextRefresh()
    }
  }, [refresh, enabled, scheduleNextRefresh])

  // Start/stop refresh
  useEffect(() => {
    if (enabled) {
      scheduleNextRefresh()
    } else if (intervalRef.current) {
      clearTimeout(intervalRef.current)
      intervalRef.current = null
    }

    return () => {
      if (intervalRef.current) {
        clearTimeout(intervalRef.current)
      }
    }
  }, [enabled, scheduleNextRefresh])

  return {
    ...state,
    refresh: manualRefresh,
    pause: () => {
      if (intervalRef.current) {
        clearTimeout(intervalRef.current)
        intervalRef.current = null
      }
    },
    resume: scheduleNextRefresh
  }
}

/**
 * Hook for smart refresh based on user activity
 */
export const useSmartRefresh = (
  machines: Machine[],
  teamName: string
) => {
  const [lastActivity, setLastActivity] = useState(Date.now())
  const [refreshInterval, setRefreshInterval] = useState(30000) // Start at 30s
  
  // Track user activity
  useEffect(() => {
    const updateActivity = () => {
      setLastActivity(Date.now())
      setRefreshInterval(30000) // Reset to fast refresh on activity
    }

    const events = ['mousedown', 'keydown', 'scroll', 'touchstart']
    events.forEach(event => {
      document.addEventListener(event, updateActivity, { passive: true })
    })

    return () => {
      events.forEach(event => {
        document.removeEventListener(event, updateActivity)
      })
    }
  }, [])

  // Adjust refresh interval based on inactivity
  useEffect(() => {
    const checkInactivity = setInterval(() => {
      const inactiveTime = Date.now() - lastActivity
      
      if (inactiveTime > 300000) { // 5 minutes
        setRefreshInterval(120000) // Slow to 2 minutes
      } else if (inactiveTime > 60000) { // 1 minute
        setRefreshInterval(60000) // Slow to 1 minute
      }
    }, 10000) // Check every 10 seconds

    return () => clearInterval(checkInactivity)
  }, [lastActivity])

  return useBackgroundRefresh(machines, teamName, {
    interval: refreshInterval,
    onlyWhenVisible: true,
    enabled: true
  })
}