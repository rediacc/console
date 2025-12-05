import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Skeleton } from 'antd';
import MachineAssignmentStatusBadge from '@/components/resources/MachineAssignmentStatusBadge';
import { MachineAssignmentService } from '../../services';
import { useMachineAssignmentStatus } from '@/api/queries/distributedStorage';
import { useComponentStyles } from '@/hooks/useComponentStyles';
import type { Machine, MachineAssignmentType } from '@/types';

interface LazyAssignmentStatusProps {
  machine: Machine;
  teamName?: string;
  priority?: 'high' | 'normal' | 'low';
  onStatusLoaded?: (status: string) => void;
}

interface IntersectionOptions {
  rootMargin?: string;
  threshold?: number | number[];
}

const PRIORITY_CONFIGS: Record<string, IntersectionOptions> = {
  high: { rootMargin: '100px', threshold: 0 },
  normal: { rootMargin: '50px', threshold: 0.1 },
  low: { rootMargin: '0px', threshold: 0.5 },
};

export const LazyAssignmentStatus: React.FC<LazyAssignmentStatusProps> = ({
  machine,
  teamName,
  priority = 'normal',
  onStatusLoaded,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const styles = useComponentStyles();

  // Quick check for immediate status (no API call needed)
  const immediateStatus = MachineAssignmentService.getMachineAssignmentType(machine);
  const needsApiCall = immediateStatus === 'CLONE';

  // Only fetch if visible and needs API call
  const { data: assignmentData, isLoading } = useMachineAssignmentStatus(
    teamName || machine.teamName,
    machine.machineName,
    isVisible && needsApiCall && !hasLoaded
  );

  // Intersection observer setup
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && !isVisible) {
          setIsVisible(true);
        }
      });
    }, PRIORITY_CONFIGS[priority]);

    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
    };
  }, [priority, isVisible]);

  // Track status loaded state during render
  const [prevAssignmentData, setPrevAssignmentData] = useState(assignmentData);
  const [prevHasLoaded, setPrevHasLoaded] = useState(hasLoaded);

  if (assignmentData !== prevAssignmentData && assignmentData && !prevHasLoaded) {
    setPrevAssignmentData(assignmentData);
    setHasLoaded(true);
    setPrevHasLoaded(true);
    if (onStatusLoaded) {
      onStatusLoaded(assignmentData.assignmentType);
    }
  }

  // Render loading skeleton
  if (!isVisible) {
    return (
      <div
        ref={containerRef}
        style={{
          height: 22,
          width: 120,
          ...styles.flexCenter,
        }}
        data-testid="lazy-status-loading-container"
      >
        <Skeleton.Input
          active
          size="small"
          style={{
            width: 120,
            height: 22,
            borderRadius: 'var(--border-radius-sm)',
          }}
          data-testid="lazy-status-skeleton"
        />
      </div>
    );
  }

  // If no API call needed, show immediate status
  if (!needsApiCall) {
    const assignmentInfo = MachineAssignmentService.getAssignmentInfo(machine);

    return (
      <div ref={containerRef} data-testid="lazy-status-immediate-container">
        <MachineAssignmentStatusBadge
          assignmentType={immediateStatus}
          assignmentDetails={assignmentInfo.resourceName}
        />
      </div>
    );
  }

  // Loading state for API call
  if (isLoading && !hasLoaded) {
    return (
      <div
        ref={containerRef}
        style={styles.flexCenter}
        data-testid="lazy-status-api-loading-container"
      >
        <Skeleton.Input
          active
          size="small"
          style={{
            width: 120,
            height: 22,
            borderRadius: 'var(--border-radius-sm)',
          }}
          data-testid="lazy-status-api-skeleton"
        />
      </div>
    );
  }

  // Show assignment data
  const finalAssignmentType =
    (assignmentData?.assignmentType as MachineAssignmentType) || immediateStatus;
  const finalResourceName =
    assignmentData?.assignmentDetails ||
    MachineAssignmentService.getAssignmentInfo(machine).resourceName;

  return (
    <div ref={containerRef} data-testid="lazy-status-final-container">
      <MachineAssignmentStatusBadge
        assignmentType={finalAssignmentType}
        assignmentDetails={finalResourceName}
      />
    </div>
  );
};

/**
 * Progressive loader for machine list status
 */
export const ProgressiveMachineStatusLoader: React.FC<{
  machines: Machine[];
  teamName?: string;
  batchSize?: number;
  batchDelay?: number;
}> = ({ machines, teamName, batchSize = 10, batchDelay = 100 }) => {
  const [loadedCount, setLoadedCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const styles = useComponentStyles();

  // Load next batch
  const loadNextBatch = useCallback(() => {
    if (isLoading || loadedCount >= machines.length) return;

    setIsLoading(true);
    setTimeout(() => {
      setLoadedCount((prev) => Math.min(prev + batchSize, machines.length));
      setIsLoading(false);
    }, batchDelay);
  }, [isLoading, loadedCount, machines.length, batchSize, batchDelay]);

  // Auto-load batches during render
  const [prevLoadedCount, setPrevLoadedCount] = useState(loadedCount);
  const [prevIsLoading, setPrevIsLoading] = useState(isLoading);

  if (
    (loadedCount !== prevLoadedCount || isLoading !== prevIsLoading) &&
    loadedCount < machines.length &&
    !isLoading
  ) {
    setPrevLoadedCount(loadedCount);
    setPrevIsLoading(isLoading);
    loadNextBatch();
  }

  return (
    <div data-testid="lazy-status-progressive-loader">
      {machines.slice(0, loadedCount).map((machine) => (
        <LazyAssignmentStatus
          key={machine.machineName}
          machine={machine}
          teamName={teamName}
          priority={loadedCount < batchSize ? 'high' : 'normal'}
        />
      ))}
      {loadedCount < machines.length && (
        <div
          style={{
            ...styles.padding.sm,
            ...styles.flexCenter,
          }}
          data-testid="lazy-status-loading-more"
        >
          <Skeleton.Button
            active
            size="small"
            style={{
              borderRadius: 'var(--border-radius-sm)',
            }}
            data-testid="lazy-status-loading-button"
          />
        </div>
      )}
    </div>
  );
};
