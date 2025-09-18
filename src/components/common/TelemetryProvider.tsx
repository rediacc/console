import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { useSelector } from 'react-redux'
import { useLocation } from 'react-router-dom'
import { selectUser, selectCompany } from '@/store/auth/authSelectors'
import { telemetryService, createTelemetryConfig } from '@/services/telemetryService'

interface TelemetryContextType {
  isInitialized: boolean
  trackEvent: (eventName: string, attributes?: Record<string, string | number | boolean>) => void
  trackUserAction: (action: string, target?: string, details?: Record<string, any>) => void
  trackPageView: (path: string, title?: string) => void
  trackError: (error: Error, context?: Record<string, any>) => void
  trackPerformance: (metric: string, value: number, unit?: string) => void
  measureAndTrack: <T>(name: string, fn: () => T | Promise<T>) => T | Promise<T>
}

const TelemetryContext = createContext<TelemetryContextType | null>(null)

interface TelemetryProviderProps {
  children: ReactNode
}

export const TelemetryProvider: React.FC<TelemetryProviderProps> = ({ children }) => {
  const [isInitialized, setIsInitialized] = useState(false)
  const user = useSelector(selectUser)
  const company = useSelector(selectCompany)
  const location = useLocation()

  // Initialize telemetry service
  useEffect(() => {
    const initializeTelemetry = async () => {
      try {
        const config = createTelemetryConfig()
        await telemetryService.initialize(config)
        setIsInitialized(true)

        // Store session start time for logout tracking
        if (typeof window !== 'undefined') {
          (window as any).sessionStartTime = Date.now()
        }

        console.log('🔍 Telemetry successfully initialized')
      } catch (error) {
        console.error('Failed to initialize telemetry:', error)
        // Set initialized to false but don't crash the app
        setIsInitialized(false)
      }
    }

    // Add error boundary for the initialization
    initializeTelemetry().catch((error) => {
      console.error('Telemetry initialization failed catastrophically:', error)
      setIsInitialized(false)
    })

    // Cleanup on unmount
    return () => {
      try {
        telemetryService.shutdown()
      } catch (error) {
        console.warn('Error during telemetry shutdown:', error)
      }
    }
  }, [])

  // Update user context when auth state changes
  useEffect(() => {
    if (isInitialized && user) {
      telemetryService.setUserContext({
        email: user.email,
        company: company,
        // Note: We don't pass the actual user ID for privacy, just the email domain
      })
    }
  }, [isInitialized, user, company])

  // Track page views
  useEffect(() => {
    if (isInitialized) {
      telemetryService.trackPageView(location.pathname, document.title)
    }
  }, [isInitialized, location.pathname])

  // Enhanced performance monitoring with Core Web Vitals
  useEffect(() => {
    if (!isInitialized || typeof window === 'undefined') return

    // Track Core Web Vitals using the web-vitals library
    const trackWebVitals = async () => {
      try {
        // Try to use web-vitals library if available
        if ('webVitals' in window) {
          // @ts-ignore - web-vitals might be loaded globally
          const { getCLS, getFID, getFCP, getLCP, getTTFB, onINP } = window.webVitals

          getCLS((metric: any) => {
            telemetryService.trackPerformance('web_vitals.cls', metric.value, 'score')
          })

          getFID((metric: any) => {
            telemetryService.trackPerformance('web_vitals.fid', metric.value, 'ms')
          })

          getFCP((metric: any) => {
            telemetryService.trackPerformance('web_vitals.fcp', metric.value, 'ms')
          })

          getLCP((metric: any) => {
            telemetryService.trackPerformance('web_vitals.lcp', metric.value, 'ms')
          })

          getTTFB((metric: any) => {
            telemetryService.trackPerformance('web_vitals.ttfb', metric.value, 'ms')
          })

          // Track Interaction to Next Paint (INP) - newer metric
          if (onINP) {
            onINP((metric: any) => {
              telemetryService.trackPerformance('web_vitals.inp', metric.value, 'ms')
            })
          }
        } else {
          // Fallback to Performance Observer
          trackBasicPerformanceMetrics()
        }
      } catch (error) {
        console.warn('Web Vitals tracking failed, falling back to basic metrics:', error)
        trackBasicPerformanceMetrics()
      }
    }

    const trackBasicPerformanceMetrics = () => {
      if ('PerformanceObserver' in window) {
        try {
          // Navigation timing
          const navObserver = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry) => {
              if (entry.entryType === 'navigation') {
                const navEntry = entry as PerformanceNavigationTiming
                telemetryService.trackPerformance('page.load.total', navEntry.loadEventEnd - navEntry.fetchStart)
                telemetryService.trackPerformance('page.load.dom_content', navEntry.domContentLoadedEventEnd - navEntry.fetchStart)
                telemetryService.trackPerformance('page.load.first_paint', navEntry.loadEventStart - navEntry.fetchStart)

                // Time to First Byte (TTFB)
                telemetryService.trackPerformance('page.load.ttfb', navEntry.responseStart - navEntry.requestStart)

                // DNS lookup time
                telemetryService.trackPerformance('page.load.dns', navEntry.domainLookupEnd - navEntry.domainLookupStart)

                // TCP connection time
                telemetryService.trackPerformance('page.load.tcp', navEntry.connectEnd - navEntry.connectStart)

                // SSL handshake time
                if (navEntry.secureConnectionStart > 0) {
                  telemetryService.trackPerformance('page.load.ssl', navEntry.connectEnd - navEntry.secureConnectionStart)
                }
              }
            })
          })
          navObserver.observe({ entryTypes: ['navigation'] })

          // Paint timing
          const paintObserver = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry) => {
              telemetryService.trackPerformance(`page.paint.${entry.name.replace('-', '_')}`, entry.startTime)
            })
          })
          paintObserver.observe({ entryTypes: ['paint'] })

          // Largest Contentful Paint (LCP)
          const lcpObserver = new PerformanceObserver((list) => {
            const entries = list.getEntries()
            const lastEntry = entries[entries.length - 1]
            telemetryService.trackPerformance('web_vitals.lcp_fallback', lastEntry.startTime)
          })
          lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] })

          // First Input Delay approximation
          const fidObserver = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry) => {
              const firstInputEntry = entry as any
              const fid = firstInputEntry.processingStart - firstInputEntry.startTime
              telemetryService.trackPerformance('web_vitals.fid_fallback', fid)
            })
          })
          fidObserver.observe({ entryTypes: ['first-input'] })

          // Layout Shift (CLS)
          let clsValue = 0
          const clsObserver = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry: any) => {
              if (!entry.hadRecentInput) {
                clsValue += entry.value
              }
            })
          })
          clsObserver.observe({ entryTypes: ['layout-shift'] })

          // Report CLS on page visibility change
          const reportCLS = () => {
            telemetryService.trackPerformance('web_vitals.cls_fallback', clsValue, 'score')
          }

          document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
              reportCLS()
            }
          })

          // Report CLS on page unload
          window.addEventListener('beforeunload', reportCLS)

          // Resource timing for critical resources
          const resourceObserver = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry) => {
              const resource = entry as PerformanceResourceTiming
              if (resource.initiatorType === 'script' || resource.initiatorType === 'link') {
                telemetryService.trackPerformance(
                  `resource.${resource.initiatorType}.duration`,
                  resource.responseEnd - resource.startTime
                )
              }
            })
          })
          resourceObserver.observe({ entryTypes: ['resource'] })

          // Long tasks
          const longTaskObserver = new PerformanceObserver((list) => {
            list.getEntries().forEach((entry) => {
              telemetryService.trackPerformance('page.long_task', entry.duration)
            })
          })
          longTaskObserver.observe({ entryTypes: ['longtask'] })

          return () => {
            navObserver.disconnect()
            paintObserver.disconnect()
            lcpObserver.disconnect()
            fidObserver.disconnect()
            clsObserver.disconnect()
            resourceObserver.disconnect()
            longTaskObserver.disconnect()
          }
        } catch (error) {
          console.warn('Performance Observer setup failed:', error)
        }
      }
    }

    trackWebVitals()
  }, [isInitialized])

  // Global error tracking with enhanced context
  useEffect(() => {
    if (!isInitialized) return

    const handleError = (event: ErrorEvent) => {
      telemetryService.trackError(new Error(event.message), {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        source: 'window.onerror',
        user_agent: navigator.userAgent,
        page_url: window.location.href,
        timestamp: Date.now(),
      })
    }

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const error = event.reason instanceof Error ? event.reason : new Error(String(event.reason))
      telemetryService.trackError(error, {
        source: 'unhandledrejection',
        promise_rejection: true,
        page_url: window.location.href,
        timestamp: Date.now(),
      })
    }

    const handleResourceError = (event: Event) => {
      const target = event.target as HTMLElement
      if (target && (target.tagName === 'IMG' || target.tagName === 'SCRIPT' || target.tagName === 'LINK')) {
        telemetryService.trackError(new Error('Resource loading failed'), {
          source: 'resource_error',
          resource_type: target.tagName.toLowerCase(),
          resource_url: (target as any).src || (target as any).href,
          page_url: window.location.href,
          timestamp: Date.now(),
        })
      }
    }

    window.addEventListener('error', handleError)
    window.addEventListener('unhandledrejection', handleUnhandledRejection)
    window.addEventListener('error', handleResourceError, true) // Capture phase for resource errors

    return () => {
      window.removeEventListener('error', handleError)
      window.removeEventListener('unhandledrejection', handleUnhandledRejection)
      window.removeEventListener('error', handleResourceError, true)
    }
  }, [isInitialized])

  // Memory usage monitoring
  useEffect(() => {
    if (!isInitialized || typeof window === 'undefined') return

    const trackMemoryUsage = () => {
      if ('performance' in window && (performance as any).memory) {
        const memory = (performance as any).memory
        telemetryService.trackPerformance('browser.memory.used', memory.usedJSHeapSize, 'bytes')
        telemetryService.trackPerformance('browser.memory.total', memory.totalJSHeapSize, 'bytes')
        telemetryService.trackPerformance('browser.memory.limit', memory.jsHeapSizeLimit, 'bytes')
      }
    }

    // Track memory usage periodically
    const memoryInterval = setInterval(trackMemoryUsage, 30000) // Every 30 seconds

    // Track memory usage on visibility change
    document.addEventListener('visibilitychange', trackMemoryUsage)

    return () => {
      clearInterval(memoryInterval)
      document.removeEventListener('visibilitychange', trackMemoryUsage)
    }
  }, [isInitialized])

  const contextValue: TelemetryContextType = {
    isInitialized,
    trackEvent: telemetryService.trackEvent.bind(telemetryService),
    trackUserAction: telemetryService.trackUserAction.bind(telemetryService),
    trackPageView: telemetryService.trackPageView.bind(telemetryService),
    trackError: telemetryService.trackError.bind(telemetryService),
    trackPerformance: telemetryService.trackPerformance.bind(telemetryService),
    measureAndTrack: telemetryService.measureAndTrack.bind(telemetryService),
  }

  return (
    <TelemetryContext.Provider value={contextValue}>
      {children}
    </TelemetryContext.Provider>
  )
}

export const useTelemetry = (): TelemetryContextType => {
  const context = useContext(TelemetryContext)
  if (!context) {
    // Return a no-op implementation if telemetry is not available
    return {
      isInitialized: false,
      trackEvent: () => {},
      trackUserAction: () => {},
      trackPageView: () => {},
      trackError: () => {},
      trackPerformance: () => {},
      measureAndTrack: <T extends any>(name: string, fn: () => T | Promise<T>): T | Promise<T> => fn(),
    }
  }
  return context
}

// Higher-order component for automatic performance tracking with SDK 2.0 patterns
export const withTelemetryTracking = <P extends object>(
  WrappedComponent: React.ComponentType<P>,
  componentName?: string
) => {
  const TrackedComponent: React.FC<P> = (props) => {
    const { measureAndTrack, trackEvent } = useTelemetry()
    const displayName = componentName || WrappedComponent.displayName || WrappedComponent.name || 'Component'

    useEffect(() => {
      trackEvent('component.render_start', { 'component.name': displayName })
      const renderStart = performance.now()

      return () => {
        const renderDuration = performance.now() - renderStart
        trackEvent('component.render_complete', {
          'component.name': displayName,
          'component.render_duration': renderDuration
        })
      }
    }, [displayName, trackEvent])

    return measureAndTrack(`component.render.${displayName}`, () => (
      <WrappedComponent {...props} />
    )) as React.ReactElement
  }

  TrackedComponent.displayName = `withTelemetryTracking(${componentName || WrappedComponent.displayName || WrappedComponent.name || 'Component'})`
  return TrackedComponent
}

// Hook for tracking component lifecycle with enhanced metrics
export const useComponentTelemetry = (componentName: string) => {
  const { trackEvent, trackPerformance } = useTelemetry()

  useEffect(() => {
    const mountTime = performance.now()
    trackEvent('component.mount', {
      'component.name': componentName,
      'component.mount_timestamp': mountTime
    })

    return () => {
      const unmountTime = performance.now()
      const lifetime = unmountTime - mountTime

      trackEvent('component.unmount', {
        'component.name': componentName,
        'component.unmount_timestamp': unmountTime
      })

      trackPerformance(`component.lifetime.${componentName}`, lifetime)
    }
  }, [componentName, trackEvent, trackPerformance])
}

// Hook for tracking user interactions with UI elements (enhanced)
export const useInteractionTracking = () => {
  const { trackUserAction, trackEvent } = useTelemetry()

  const trackClick = (target: string, details?: Record<string, any>) => {
    trackUserAction('click', target, {
      ...details,
      interaction_timestamp: Date.now(),
      page_url: window.location.href,
    })
  }

  const trackFormSubmit = (formName: string, details?: Record<string, any>) => {
    trackUserAction('form_submit', formName, {
      ...details,
      interaction_timestamp: Date.now(),
    })
  }

  const trackFormError = (formName: string, errors: Record<string, any>) => {
    trackUserAction('form_error', formName, {
      errors: JSON.stringify(errors),
      error_count: Object.keys(errors).length,
      interaction_timestamp: Date.now(),
    })
  }

  const trackModalOpen = (modalName: string, trigger?: string) => {
    trackUserAction('modal_open', modalName, {
      trigger_source: trigger,
      interaction_timestamp: Date.now(),
    })
  }

  const trackModalClose = (modalName: string, method?: string) => {
    trackUserAction('modal_close', modalName, {
      close_method: method, // 'button', 'escape', 'backdrop', etc.
      interaction_timestamp: Date.now(),
    })
  }

  const trackTabChange = (tabName: string, previousTab?: string) => {
    trackUserAction('tab_change', tabName, {
      previous_tab: previousTab,
      interaction_timestamp: Date.now(),
    })
  }

  const trackSearch = (query: string, resultsCount?: number, searchType?: string) => {
    trackUserAction('search', 'search_input', {
      query_length: query.length,
      results_count: resultsCount,
      has_results: resultsCount !== undefined && resultsCount > 0,
      search_type: searchType,
      interaction_timestamp: Date.now(),
    })
  }

  const trackFilter = (filterType: string, filterValue: string, resultCount?: number) => {
    trackUserAction('filter', filterType, {
      filter_value: filterValue,
      result_count: resultCount,
      interaction_timestamp: Date.now(),
    })
  }

  const trackTableAction = (action: string, tableName: string, details?: Record<string, any>) => {
    trackUserAction('table_action', `${tableName}.${action}`, {
      ...details,
      table_name: tableName,
      interaction_timestamp: Date.now(),
    })
  }

  const trackDownload = (fileName: string, fileType: string, fileSize?: number) => {
    trackUserAction('download', fileName, {
      file_type: fileType,
      file_size: fileSize,
      interaction_timestamp: Date.now(),
    })
  }

  return {
    trackClick,
    trackFormSubmit,
    trackFormError,
    trackModalOpen,
    trackModalClose,
    trackTabChange,
    trackSearch,
    trackFilter,
    trackTableAction,
    trackDownload,
  }
}

export default TelemetryProvider