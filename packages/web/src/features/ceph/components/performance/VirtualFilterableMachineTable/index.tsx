import React, { useCallback, useMemo, useState } from 'react';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Badge } from 'antd';
import { ActionGroup } from '@/components/common/styled';
import { MachineAssignmentService } from '@/features/ceph';
import {
  AssignmentSelect,
  Container,
  FilterInput,
  OptionLabel,
  PageSizeSelect,
  RefreshButton,
  StatusText,
  ToolbarStack,
} from '@/features/ceph/components/performance/VirtualFilterableMachineTable/styles';
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
            <OptionLabel>All Machines</OptionLabel>
          </Badge>
        ),
      },
      {
        value: 'AVAILABLE',
        label: (
          <Badge count={assignmentCounts.AVAILABLE} showZero color="green">
            <OptionLabel>Available</OptionLabel>
          </Badge>
        ),
      },
      {
        value: 'CLUSTER',
        label: (
          <Badge count={assignmentCounts.CLUSTER} showZero color="blue">
            <OptionLabel>Assigned to Cluster</OptionLabel>
          </Badge>
        ),
      },
      {
        value: 'IMAGE',
        label: (
          <Badge count={assignmentCounts.IMAGE} showZero color="purple">
            <OptionLabel>Assigned to Image</OptionLabel>
          </Badge>
        ),
      },
      {
        value: 'CLONE',
        label: (
          <Badge count={assignmentCounts.CLONE} showZero color="orange">
            <OptionLabel>Assigned to Clone</OptionLabel>
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
    <Container data-testid="filterable-machine-container">
      <ToolbarStack>
        <ActionGroup>
          <FilterInput
            data-testid="filterable-machine-search"
            prefix={<SearchOutlined />}
            placeholder="Search machines..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            allowClear
          />

          <AssignmentSelect
            data-testid="filterable-machine-filter-assignment"
            value={assignmentFilter}
            onChange={(value) => setAssignmentFilter(value as MachineAssignmentType | 'ALL')}
            placeholder="Filter by assignment"
            options={assignmentOptions}
          />

          <PageSizeSelect
            data-testid="filterable-machine-page-size"
            value={pageSize}
            onChange={(value) => setPageSize(Number(value))}
            options={pageSizeOptions}
          />

          {onRefresh && (
            <RefreshButton
              icon={<ReloadOutlined />}
              data-testid="filterable-machine-refresh"
              onClick={onRefresh}
              loading={loading}
              aria-label="Refresh machines"
            >
              Refresh
            </RefreshButton>
          )}
        </ActionGroup>

        <StatusText data-testid="filterable-machine-status">
          Showing {displayedMachines.length} of {filteredMachines.length} machines
          {hasMore && ' (scroll to load more)'}
        </StatusText>
      </ToolbarStack>

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
    </Container>
  );
};
