import React, { useCallback, useMemo, useState } from 'react';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Badge, Button, Flex, Input, Select } from 'antd';
import { MachineAssignmentService } from '@/features/ceph';
import { VirtualMachineTable } from '@/features/ceph/components/performance/VirtualMachineTable';
import { useDebounce } from '@/features/ceph/utils/useDebounce';
import { Machine, MachineAssignmentType } from '@/types';

interface VirtualFilterableMachineTableProps {
  machines: Machine[];
  loading?: boolean;
  teamName?: string;
  onRefresh?: () => void;
  selectable?: boolean;
  onRowClick?: (machine: Machine) => void;
  renderActions?: (machine: Machine) => React.ReactNode;
  height?: number;
}

export const VirtualFilterableMachineTable: React.FC<VirtualFilterableMachineTableProps> = ({
  machines,
  loading = false,
  teamName: _teamName,
  onRefresh,
  selectable = true,
  onRowClick,
  renderActions,
  height = 600,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [assignmentFilter, setAssignmentFilter] = useState<MachineAssignmentType | 'ALL'>('ALL');
  const [pageSize, setPageSize] = useState(100);
  const [displayedCount, setDisplayedCount] = useState(100);

  const debouncedSearch = useDebounce(searchQuery, 300);

  const filteredMachines = useMemo(() => {
    if (!machines || !Array.isArray(machines)) {
      return [];
    }

    let result = machines;

    if (assignmentFilter !== 'ALL') {
      result = result.filter((machine) => {
        const assignmentType = MachineAssignmentService.getMachineAssignmentType(machine);
        return assignmentType === assignmentFilter;
      });
    }

    if (debouncedSearch) {
      const searchLower = debouncedSearch.toLowerCase();
      result = result.filter(
        (machine) =>
          machine.machineName.toLowerCase().includes(searchLower) ||
          machine.teamName?.toLowerCase().includes(searchLower) ||
          machine.cephClusterName?.toLowerCase().includes(searchLower)
      );
    }

    return result;
  }, [machines, assignmentFilter, debouncedSearch]);

  const assignmentCounts = useMemo(() => {
    const counts: Record<MachineAssignmentType | 'ALL', number> = {
      ALL: machines.length,
      AVAILABLE: 0,
      CLUSTER: 0,
      IMAGE: 0,
      CLONE: 0,
    };

    machines.forEach((machine) => {
      const type = MachineAssignmentService.getMachineAssignmentType(machine);
      counts[type] += 1;
    });

    return counts;
  }, [machines]);

  const displayedMachines = useMemo(
    () => filteredMachines.slice(0, displayedCount),
    [filteredMachines, displayedCount]
  );

  const loadMore = useCallback(async () => {
    await new Promise((resolve) => setTimeout(resolve, 100));
    setDisplayedCount((prev) => Math.min(prev + pageSize, filteredMachines.length));
  }, [pageSize, filteredMachines.length]);

  const [prevDebouncedSearch, setPrevDebouncedSearch] = useState(debouncedSearch);
  const [prevAssignmentFilter, setPrevAssignmentFilter] = useState(assignmentFilter);
  const [prevPageSize, setPrevPageSize] = useState(pageSize);

  if (
    debouncedSearch !== prevDebouncedSearch ||
    assignmentFilter !== prevAssignmentFilter ||
    pageSize !== prevPageSize
  ) {
    setPrevDebouncedSearch(debouncedSearch);
    setPrevAssignmentFilter(assignmentFilter);
    setPrevPageSize(pageSize);
    setDisplayedCount(pageSize);
  }

  const hasMore = displayedCount < filteredMachines.length;

  const assignmentOptions = useMemo(
    () => [
      {
        value: 'ALL',
        label: (
          <Badge count={assignmentCounts.ALL} showZero color="blue">
            <span>All Machines</span>
          </Badge>
        ),
      },
      {
        value: 'AVAILABLE',
        label: (
          <Badge count={assignmentCounts.AVAILABLE} showZero color="green">
            <span>Available</span>
          </Badge>
        ),
      },
      {
        value: 'CLUSTER',
        label: (
          <Badge count={assignmentCounts.CLUSTER} showZero color="blue">
            <span>Assigned to Cluster</span>
          </Badge>
        ),
      },
      {
        value: 'IMAGE',
        label: (
          <Badge count={assignmentCounts.IMAGE} showZero color="purple">
            <span>Assigned to Image</span>
          </Badge>
        ),
      },
      {
        value: 'CLONE',
        label: (
          <Badge count={assignmentCounts.CLONE} showZero color="orange">
            <span>Assigned to Clone</span>
          </Badge>
        ),
      },
    ],
    [assignmentCounts]
  );

  const pageSizeOptions = useMemo(
    () => [
      { value: 50, label: '50 per batch' },
      { value: 100, label: '100 per batch' },
      { value: 200, label: '200 per batch' },
      { value: 500, label: '500 per batch' },
    ],
    []
  );

  return (
    <Flex vertical gap={12} data-testid="filterable-machine-container">
      <Flex vertical gap={8}>
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Input
            style={{ width: 'min(360px, 100%)', maxWidth: '100%' }}
            data-testid="filterable-machine-search"
            prefix={<SearchOutlined />}
            placeholder="Search machines..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            allowClear
          />

          <Select
            style={{ width: 'min(200px, 100%)' }}
            data-testid="filterable-machine-filter-assignment"
            value={assignmentFilter}
            onChange={(value) => setAssignmentFilter(value as MachineAssignmentType | 'ALL')}
            placeholder="Filter by assignment"
            options={assignmentOptions}
          />

          <Select
            style={{ width: 'min(200px, 100%)' }}
            data-testid="filterable-machine-page-size"
            value={pageSize}
            onChange={(value) => setPageSize(Number(value))}
            options={pageSizeOptions}
          />

          {onRefresh && (
            <Button
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                minWidth: 48,
                minHeight: 40,
              }}
              icon={<ReloadOutlined />}
              data-testid="filterable-machine-refresh"
              onClick={onRefresh}
              loading={loading}
              aria-label="Refresh machines"
            >
              Refresh
            </Button>
          )}
        </div>

        <div
          style={{ fontSize: 14, color: 'var(--ant-color-text-secondary)' }}
          data-testid="filterable-machine-status"
        >
          Showing {displayedMachines.length} of {filteredMachines.length} machines
          {hasMore && ' (scroll to load more)'}
        </div>
      </Flex>

      <div data-testid="filterable-machine-table">
        <VirtualMachineTable
          machines={displayedMachines}
          loading={loading}
          hasMore={hasMore}
          loadMore={loadMore}
          height={height}
          selectable={selectable}
          onRowClick={onRowClick}
          renderActions={renderActions}
        />
      </div>
    </Flex>
  );
};
