import type { LayoutShiftEntry, WebVitalsMetric } from './types';

function setupWebVitalsObserver(
  trackWebVitals: (metric: WebVitalsMetric) => void
): PerformanceObserver | null {
  if (!('PerformanceObserver' in window)) {
    return null;
  }

  // Cumulative Layout Shift observer
  const clsObserver = new PerformanceObserver((list) => {
    let clsValue = 0;
    list.getEntries().forEach((entry) => {
      const layoutEntry = entry as LayoutShiftEntry;
      if (!layoutEntry.hadRecentInput) {
        clsValue += layoutEntry.value;
      }
    });
    if (clsValue > 0) {
      // Determine CLS rating based on thresholds
      let clsRating: 'good' | 'needs-improvement' | 'poor';
      if (clsValue <= 0.1) {
        clsRating = 'good';
      } else if (clsValue <= 0.25) {
        clsRating = 'needs-improvement';
      } else {
        clsRating = 'poor';
      }

      trackWebVitals({
        name: 'CLS',
        value: clsValue,
        rating: clsRating,
        id: `cls-${Date.now()}`,
      });
    }
  });

  try {
    clsObserver.observe({ entryTypes: ['layout-shift'] });
    return clsObserver;
  } catch (error) {
    console.warn('Layout shift observation not supported', error);
    return null;
  }
}

export function initializeWebVitals(
  trackWebVitals: (metric: WebVitalsMetric) => void
): PerformanceObserver | null {
  // Use the web-vitals library for accurate Core Web Vitals measurement
  if (typeof window !== 'undefined' && 'web-vitals' in window) {
    // This would be imported from web-vitals package
    console.warn('Web Vitals tracking enabled - implement with web-vitals package');
    return null;
  }

  // Fallback to manual performance observer
  return setupWebVitalsObserver(trackWebVitals);
}
