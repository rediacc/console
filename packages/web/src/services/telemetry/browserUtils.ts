import type { ExtendedPerformance, NavigatorConnection, WindowNavigation } from './types';

// Re-export shared utilities
export { extractApiEndpoint, generateSessionId } from '@rediacc/shared/telemetry';

export function getBrowserName(): string {
  const userAgent = navigator.userAgent;
  if (userAgent.includes('Chrome') && !userAgent.includes('Edge')) return 'chrome';
  if (userAgent.includes('Firefox')) return 'firefox';
  if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) return 'safari';
  if (userAgent.includes('Edge')) return 'edge';
  if (userAgent.includes('Opera')) return 'opera';
  return 'unknown';
}

export function getBrowserVersion(): string {
  const userAgent = navigator.userAgent;
  const match = /(Chrome|Firefox|Safari|Edge|Opera)\/(\d+\.\d+)/.exec(userAgent);
  return match ? match[2] : 'unknown';
}

export function getPlatform(): string {
  try {
    // Try modern userAgentData API first (Chrome 90+, Edge 90+)
    const navigatorWithUAData = navigator as Navigator & {
      userAgentData?: { platform?: string };
    };
    if (navigatorWithUAData.userAgentData?.platform) {
      return navigatorWithUAData.userAgentData.platform;
    }
    // Fall back to parsing userAgent
    const userAgent = navigator.userAgent;
    if (userAgent.includes('Windows')) return 'Windows';
    if (userAgent.includes('Mac')) return 'macOS';
    if (userAgent.includes('Linux')) return 'Linux';
    if (userAgent.includes('Android')) return 'Android';
    if (userAgent.includes('iOS') || userAgent.includes('iPhone') || userAgent.includes('iPad'))
      return 'iOS';
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

export function getNavigationType(): string {
  try {
    const navigation = (window as Window & { navigation?: WindowNavigation }).navigation;
    if (navigation?.type) {
      return String(navigation.type);
    }
    if ('performance' in window) {
      const entries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
      if (entries.length > 0) {
        return entries[0].type;
      }
    }
  } catch (error) {
    console.warn('Failed to get navigation type:', error);
  }
  return 'unknown';
}

export function getPageLoadTime(): number {
  try {
    if ('performance' in window) {
      const entries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
      if (entries.length > 0) {
        const navTiming = entries[0];
        return navTiming.loadEventEnd - navTiming.startTime;
      }
    }
  } catch (error) {
    console.warn('Failed to get page load time:', error);
  }
  return 0;
}

export function getPerformanceAttributes(): Record<string, number | string> {
  const attributes: Record<string, number | string> = {};

  try {
    if ('performance' in window) {
      const perf = performance as ExtendedPerformance;
      if (perf.memory) {
        attributes['browser.memory.used'] = perf.memory.usedJSHeapSize || 0;
        attributes['browser.memory.total'] = perf.memory.totalJSHeapSize || 0;
        attributes['browser.memory.limit'] = perf.memory.jsHeapSizeLimit || 0;
      }
    }

    const navigatorWithConnection = navigator as Navigator & { connection?: NavigatorConnection };
    const connection = navigatorWithConnection.connection;
    if (connection) {
      attributes['network.effective_type'] = connection.effectiveType ?? 'unknown';
      attributes['network.downlink'] = connection.downlink ?? 0;
      attributes['network.rtt'] = connection.rtt ?? 0;
    }
  } catch (error) {
    console.warn('Failed to get performance attributes:', error);
  }

  return attributes;
}
