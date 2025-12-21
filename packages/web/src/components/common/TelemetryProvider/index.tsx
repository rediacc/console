import React, { createContext, type ReactNode, useContext, useEffect, useState } from 'react';
import { useSelector } from 'react-redux';
import { useLocation } from 'react-router-dom';
import { createTelemetryConfig, telemetryService } from '@/services/telemetryService';
import { selectCompany, selectUser } from '@/store/auth/authSelectors';

type TelemetryAttributes = Record<string, string | number | boolean>;

interface TelemetryContextType {
  isInitialized: boolean;
  trackEvent: (eventName: string, attributes?: TelemetryAttributes) => void;
  trackUserAction: (action: string, target?: string, details?: TelemetryAttributes) => void;
  trackPageView: (path: string, title?: string) => void;
  trackError: (error: Error, context?: TelemetryAttributes) => void;
  trackPerformance: (metric: string, value: number, unit?: string) => void;
  measureAndTrack: <T>(name: string, fn: () => T | Promise<T>) => T | Promise<T>;
}

interface TelemetryProviderProps {
  children: ReactNode;
}

interface PerformanceMemoryInfo {
  usedJSHeapSize: number;
  totalJSHeapSize: number;
  jsHeapSizeLimit: number;
}

interface PerformanceWithMemory extends Performance {
  memory?: PerformanceMemoryInfo;
}

interface WebVitalsMetric {
  value: number;
}

type WebVitalsMetricHandler = (metric: WebVitalsMetric) => void;

interface WebVitalsGlobal {
  getCLS: (callback: WebVitalsMetricHandler) => void;
  getFID: (callback: WebVitalsMetricHandler) => void;
  getFCP: (callback: WebVitalsMetricHandler) => void;
  getLCP: (callback: WebVitalsMetricHandler) => void;
  getTTFB: (callback: WebVitalsMetricHandler) => void;
  onINP?: (callback: WebVitalsMetricHandler) => void;
}

type ResourceElement = HTMLImageElement | HTMLScriptElement | HTMLLinkElement;

type LayoutShiftEntry = PerformanceEntry & {
  value: number;
  hadRecentInput?: boolean;
};

const TelemetryContext = createContext<TelemetryContextType | null>(null);

const getPageUrl = () => (typeof window === 'undefined' ? 'unknown' : window.location.href);
const getUserAgent = () => (typeof navigator === 'undefined' ? 'unknown' : navigator.userAgent);

const isResourceElement = (target: EventTarget | null): target is ResourceElement =>
  target instanceof HTMLImageElement ||
  target instanceof HTMLScriptElement ||
  target instanceof HTMLLinkElement;

const getResourceUrl = (element: ResourceElement): string | undefined => {
  if (element instanceof HTMLLinkElement) {
    return element.href;
  }
  return element.src;
};

declare global {
  interface Window {
    sessionStartTime?: number;
    webVitals?: WebVitalsGlobal;
  }
}

export const TelemetryProvider: React.FC<TelemetryProviderProps> = ({ children }) => {
  const [isInitialized, setIsInitialized] = useState(false);
  const user = useSelector(selectUser);
  const company = useSelector(selectCompany);
  const location = useLocation();

  useEffect(() => {
    const initializeTelemetry = async () => {
      try {
        const config = createTelemetryConfig();
        await telemetryService.initialize(config);
        setIsInitialized(true);

        if (typeof window !== 'undefined') {
          window.sessionStartTime = Date.now();
        }
      } catch (error) {
        console.error('Failed to initialize telemetry:', error);
        setIsInitialized(false);
      }
    };

    initializeTelemetry().catch((error) => {
      console.error('Telemetry initialization failed catastrophically:', error);
      setIsInitialized(false);
    });

    return () => {
      try {
        telemetryService.shutdown();
      } catch (error) {
        console.warn('Error during telemetry shutdown:', error);
      }
    };
  }, []);

  useEffect(() => {
    if (isInitialized && user) {
      telemetryService.setUserContext({
        email: user.email,
        company: company ?? undefined,
      });
    }
  }, [isInitialized, user, company]);

  useEffect(() => {
    if (isInitialized) {
      telemetryService.trackPageView(location.pathname, document.title);
    }
  }, [isInitialized, location.pathname]);

  useEffect(() => {
    if (!isInitialized || typeof window === 'undefined') {
      return;
    }

    const observers: PerformanceObserver[] = [];

    const trackBasicPerformanceMetrics = () => {
      if (!('PerformanceObserver' in window)) {
        return;
      }

      const navObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          if (entry.entryType === 'navigation') {
            const navEntry = entry as PerformanceNavigationTiming;
            telemetryService.trackPerformance(
              'page.load.total',
              navEntry.loadEventEnd - navEntry.fetchStart
            );
            telemetryService.trackPerformance(
              'page.load.dom_content',
              navEntry.domContentLoadedEventEnd - navEntry.fetchStart
            );
            telemetryService.trackPerformance(
              'page.load.first_paint',
              navEntry.loadEventStart - navEntry.fetchStart
            );
            telemetryService.trackPerformance(
              'page.load.ttfb',
              navEntry.responseStart - navEntry.requestStart
            );
            telemetryService.trackPerformance(
              'page.load.dns',
              navEntry.domainLookupEnd - navEntry.domainLookupStart
            );
            telemetryService.trackPerformance(
              'page.load.tcp',
              navEntry.connectEnd - navEntry.connectStart
            );
            if (navEntry.secureConnectionStart > 0) {
              telemetryService.trackPerformance(
                'page.load.ssl',
                navEntry.connectEnd - navEntry.secureConnectionStart
              );
            }
          }
        });
      });
      navObserver.observe({ entryTypes: ['navigation'] });
      observers.push(navObserver);

      const paintObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          telemetryService.trackPerformance(
            `page.paint.${entry.name.replace('-', '_')}`,
            entry.startTime
          );
        });
      });
      paintObserver.observe({ entryTypes: ['paint'] });
      observers.push(paintObserver);

      const lcpObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const lastEntry = entries[entries.length - 1];
        if (lastEntry) {
          telemetryService.trackPerformance('web_vitals.lcp_fallback', lastEntry.startTime);
        }
      });
      lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
      observers.push(lcpObserver);

      const fidObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          const firstInputEntry = entry as PerformanceEventTiming;
          const fid = firstInputEntry.processingStart - firstInputEntry.startTime;
          telemetryService.trackPerformance('web_vitals.fid_fallback', fid);
        });
      });
      fidObserver.observe({ entryTypes: ['first-input'] });
      observers.push(fidObserver);

      let clsValue = 0;
      const clsObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          const layoutShiftEntry = entry as LayoutShiftEntry;
          if (!layoutShiftEntry.hadRecentInput) {
            clsValue += layoutShiftEntry.value;
          }
        });
      });
      clsObserver.observe({ entryTypes: ['layout-shift'] });
      observers.push(clsObserver);

      const reportCLS = () => {
        telemetryService.trackPerformance('web_vitals.cls_fallback', clsValue, 'score');
      };

      const handleVisibilityChange = () => {
        if (document.visibilityState === 'hidden') {
          reportCLS();
        }
      };

      document.addEventListener('visibilitychange', handleVisibilityChange);
      window.addEventListener('beforeunload', reportCLS);

      const resourceObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          const resource = entry as PerformanceResourceTiming;
          if (resource.initiatorType === 'script' || resource.initiatorType === 'link') {
            telemetryService.trackPerformance(
              `resource.${resource.initiatorType}.duration`,
              resource.responseEnd - resource.startTime
            );
          }
        });
      });
      resourceObserver.observe({ entryTypes: ['resource'] });
      observers.push(resourceObserver);

      const longTaskObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          telemetryService.trackPerformance('page.long_task', entry.duration);
        });
      });
      longTaskObserver.observe({ entryTypes: ['longtask'] });
      observers.push(longTaskObserver);

      return () => {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        window.removeEventListener('beforeunload', reportCLS);
      };
    };

    const cleanupVisibilityListeners = trackBasicPerformanceMetrics();

    const trackWebVitals = () => {
      try {
        const webVitals = window.webVitals;
        if (webVitals) {
          const { getCLS, getFID, getFCP, getLCP, getTTFB, onINP } = webVitals;

          getCLS((metric) => {
            telemetryService.trackPerformance('web_vitals.cls', metric.value, 'score');
          });
          getFID((metric) => {
            telemetryService.trackPerformance('web_vitals.fid', metric.value, 'ms');
          });
          getFCP((metric) => {
            telemetryService.trackPerformance('web_vitals.fcp', metric.value, 'ms');
          });
          getLCP((metric) => {
            telemetryService.trackPerformance('web_vitals.lcp', metric.value, 'ms');
          });
          getTTFB((metric) => {
            telemetryService.trackPerformance('web_vitals.ttfb', metric.value, 'ms');
          });

          if (onINP) {
            onINP((metric) => {
              telemetryService.trackPerformance('web_vitals.inp', metric.value, 'ms');
            });
          }
        } else {
          trackBasicPerformanceMetrics();
        }
      } catch (error) {
        console.warn('Web Vitals tracking failed, falling back to basic metrics:', error);
        trackBasicPerformanceMetrics();
      }
    };

    trackWebVitals();

    return () => {
      cleanupVisibilityListeners?.();
      observers.forEach((observer) => observer.disconnect());
    };
  }, [isInitialized]);

  useEffect(() => {
    if (!isInitialized) {
      return;
    }

    const handleError = (event: ErrorEvent) => {
      telemetryService.trackError(new Error(event.message), {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        source: 'window.onerror',
        user_agent: getUserAgent(),
        page_url: getPageUrl(),
        timestamp: Date.now(),
      });
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const error = event.reason instanceof Error ? event.reason : new Error(String(event.reason));
      telemetryService.trackError(error, {
        source: 'unhandledrejection',
        promise_rejection: true,
        page_url: getPageUrl(),
        timestamp: Date.now(),
      });
    };

    const handleResourceError = (event: Event) => {
      const target = event.target;
      if (isResourceElement(target)) {
        const resourceUrl = getResourceUrl(target) ?? 'unknown';
        telemetryService.trackError(new Error('Resource loading failed'), {
          source: 'resource_error',
          resource_type: target.tagName.toLowerCase(),
          resource_url: resourceUrl,
          page_url: getPageUrl(),
          timestamp: Date.now(),
        });
      }
    };

    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    window.addEventListener('error', handleResourceError, true);

    return () => {
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
      window.removeEventListener('error', handleResourceError, true);
    };
  }, [isInitialized]);

  useEffect(() => {
    if (!isInitialized || typeof window === 'undefined') {
      return;
    }

    const trackMemoryUsage = () => {
      const performanceWithMemory = performance as PerformanceWithMemory;
      if (performanceWithMemory.memory) {
        telemetryService.trackPerformance(
          'browser.memory.used',
          performanceWithMemory.memory.usedJSHeapSize,
          'bytes'
        );
        telemetryService.trackPerformance(
          'browser.memory.total',
          performanceWithMemory.memory.totalJSHeapSize,
          'bytes'
        );
        telemetryService.trackPerformance(
          'browser.memory.limit',
          performanceWithMemory.memory.jsHeapSizeLimit,
          'bytes'
        );
      }
    };

    const memoryInterval = window.setInterval(trackMemoryUsage, 30000);
    document.addEventListener('visibilitychange', trackMemoryUsage);

    return () => {
      window.clearInterval(memoryInterval);
      document.removeEventListener('visibilitychange', trackMemoryUsage);
    };
  }, [isInitialized]);

  const contextValue: TelemetryContextType = {
    isInitialized,
    trackEvent: telemetryService.trackEvent.bind(telemetryService),
    trackUserAction: telemetryService.trackUserAction.bind(telemetryService),
    trackPageView: telemetryService.trackPageView.bind(telemetryService),
    trackError: telemetryService.trackError.bind(telemetryService),
    trackPerformance: telemetryService.trackPerformance.bind(telemetryService),
    measureAndTrack: telemetryService.measureAndTrack.bind(telemetryService),
  };

  return (
    <TelemetryContext.Provider value={contextValue}>
      <div style={{ display: 'contents' }}>{children}</div>
    </TelemetryContext.Provider>
  );
};

export const useTelemetry = (): TelemetryContextType => {
  const context = useContext(TelemetryContext);
  if (!context) {
    return {
      isInitialized: false,
      trackEvent: () => {},
      trackUserAction: () => {},
      trackPageView: () => {},
      trackError: () => {},
      trackPerformance: () => {},
      measureAndTrack: <T,>(_name: string, fn: () => T | Promise<T>): T | Promise<T> => fn(),
    };
  }
  return context;
};

export const withTelemetryTracking = <P extends object>(
  WrappedComponent: React.ComponentType<P>,
  _componentName?: string
) => {
  const TrackedComponent: React.FC<P> = (props) => {
    const { measureAndTrack, trackEvent } = useTelemetry();
    const displayName =
      _componentName || WrappedComponent.displayName || WrappedComponent.name || 'Component';

    useEffect(() => {
      trackEvent('component.render_start', { 'component.name': displayName });
      const renderStart = performance.now();

      return () => {
        const renderDuration = performance.now() - renderStart;
        trackEvent('component.render_complete', {
          'component.name': displayName,
          'component.render_duration': renderDuration,
        });
      };
    }, [displayName, trackEvent]);

    return measureAndTrack(`component.render.${displayName}`, () => (
      <WrappedComponent {...props} />
    )) as React.ReactElement;
  };

  TrackedComponent.displayName = `withTelemetryTracking(${
    _componentName || WrappedComponent.displayName || WrappedComponent.name || 'Component'
  })`;
  return TrackedComponent;
};

export const useComponentTelemetry = (componentName: string) => {
  const { trackEvent, trackPerformance } = useTelemetry();

  useEffect(() => {
    const mountTime = performance.now();
    trackEvent('component.mount', {
      'component.name': componentName,
      'component.mount_timestamp': mountTime,
    });

    return () => {
      const unmountTime = performance.now();
      const lifetime = unmountTime - mountTime;

      trackEvent('component.unmount', {
        'component.name': componentName,
        'component.unmount_timestamp': unmountTime,
      });

      trackPerformance(`component.lifetime.${componentName}`, lifetime);
    };
  }, [componentName, trackEvent, trackPerformance]);
};

export const useInteractionTracking = () => {
  const { trackUserAction } = useTelemetry();

  const trackClick = (target: string, details?: TelemetryAttributes) => {
    trackUserAction('click', target, {
      ...(details ?? {}),
      interaction_timestamp: Date.now(),
      page_url: getPageUrl(),
    });
  };

  const trackFormSubmit = (formName: string, details?: TelemetryAttributes) => {
    trackUserAction('form_submit', formName, {
      ...(details ?? {}),
      interaction_timestamp: Date.now(),
    });
  };

  const trackFormError = (formName: string, errors: Record<string, unknown>) => {
    trackUserAction('form_error', formName, {
      errors: JSON.stringify(errors),
      error_count: Object.keys(errors).length,
      interaction_timestamp: Date.now(),
    });
  };

  const trackModalOpen = (modalName: string, trigger?: string) => {
    trackUserAction('modal_open', modalName, {
      ...(trigger ? { trigger_source: trigger } : {}),
      interaction_timestamp: Date.now(),
    });
  };

  const trackModalClose = (modalName: string, method?: string) => {
    trackUserAction('modal_close', modalName, {
      ...(method ? { close_method: method } : {}),
      interaction_timestamp: Date.now(),
    });
  };

  const trackTabChange = (tabName: string, previousTab?: string) => {
    trackUserAction('tab_change', tabName, {
      ...(previousTab ? { previous_tab: previousTab } : {}),
      interaction_timestamp: Date.now(),
    });
  };

  const trackSearch = (query: string, resultsCount?: number, searchType?: string) => {
    const hasResults = typeof resultsCount === 'number' && resultsCount > 0;
    trackUserAction('search', 'search_input', {
      query_length: query.length,
      has_results: hasResults,
      ...(typeof resultsCount === 'number' ? { results_count: resultsCount } : {}),
      ...(searchType ? { search_type: searchType } : {}),
      interaction_timestamp: Date.now(),
    });
  };

  const trackFilter = (filterType: string, filterValue: string, resultCount?: number) => {
    trackUserAction('filter', filterType, {
      filter_value: filterValue,
      ...(typeof resultCount === 'number' ? { result_count: resultCount } : {}),
      interaction_timestamp: Date.now(),
    });
  };

  const trackTableAction = (action: string, tableName: string, details?: TelemetryAttributes) => {
    trackUserAction('table_action', `${tableName}.${action}`, {
      ...(details ?? {}),
      table_name: tableName,
      interaction_timestamp: Date.now(),
    });
  };

  const trackDownload = (fileName: string, fileType: string, fileSize?: number) => {
    trackUserAction('download', fileName, {
      file_type: fileType,
      ...(typeof fileSize === 'number' ? { file_size: fileSize } : {}),
      interaction_timestamp: Date.now(),
    });
  };

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
  };
};
