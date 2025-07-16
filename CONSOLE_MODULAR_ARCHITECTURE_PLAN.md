# Console Modular Architecture Plan

## Table of Contents
1. [Overview](#overview)
2. [Current Architecture Analysis](#current-architecture-analysis)
3. [Proposed Architecture](#proposed-architecture)
4. [Implementation Details](#implementation-details)
5. [Migration Strategy](#migration-strategy)
6. [Code Examples](#code-examples)
7. [Testing Strategy](#testing-strategy)
8. [Best Practices](#best-practices)

## Overview

This document outlines a comprehensive plan to refactor the Rediacc Console application from its current monolithic structure into a modular, scalable, and maintainable architecture. The goal is to improve code organization, enable better testing, and make the application more maintainable as it grows.

## Current Architecture Analysis

### Current Problems

1. **Monolithic Components**
   - `ResourcesPage.tsx` (1900+ lines) manages 5 different resource types:
     - Teams
     - Machines
     - Repositories
     - Bridges
     - Schedules
   - Complex state management within single components
   - Difficult to maintain and test

2. **Mixed Responsibilities**
   - Example from `ResourcesPage.tsx`:
   ```typescript
   // UI state management
   const [activeTab, setActiveTab] = useState('machines');
   
   // Business logic for queue creation
   const createQueueItem = async (params) => {
     const vaultData = buildQueueVault(params);
     const encrypted = await encryptVault(vaultData);
     return api.createQueueItem(encrypted);
   };
   
   // Direct API calls
   const machines = await getMachines({ team });
   
   // Complex rendering logic
   return <>{/* 1000+ lines of JSX */}</>;
   ```

3. **Inconsistent State Management**
   - Redux for auth and UI state
   - React Query for server state
   - Local state for complex form management
   - Services with internal state

4. **Business Logic Scattered**
   - Queue creation logic in components
   - Vault building in multiple places
   - Function execution across different files

5. **Testing Challenges**
   - Cannot test business logic without rendering components
   - Hard to mock dependencies
   - Complex setup for integration tests

### Current File Structure
```
console/
├── src/
│   ├── api/            # API layer (well organized)
│   ├── components/     # UI components (mixed concerns)
│   ├── pages/          # Page components (monolithic)
│   ├── services/       # Business services (good)
│   ├── store/          # Redux store (limited use)
│   ├── hooks/          # Custom hooks (underutilized)
│   └── utils/          # Utilities (good)
```

## Proposed Architecture

### Architecture Pattern: Feature-Driven Design with Clean Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Presentation Layer                           │
├─────────────────────────────────────────────────────────────────────┤
│  Pages (Composition)          │  Components (Pure UI)               │
│  - Route handlers             │  - Presentational components        │
│  - Layout composition         │  - No business logic                │
│  - Feature orchestration      │  - Props-driven rendering           │
├─────────────────────────────────────────────────────────────────────┤
│                       Application Layer                             │
├─────────────────────────────────────────────────────────────────────┤
│  Hooks (State Management)     │  Controllers (Orchestration)        │
│  - Feature-specific hooks     │  - Business flow coordination       │
│  - State composition          │  - Service orchestration            │
│  - Effect management          │  - Complex operations               │
├─────────────────────────────────────────────────────────────────────┤
│                          Domain Layer                               │
├─────────────────────────────────────────────────────────────────────┤
│  Models                       │  Services                           │
│  - Type definitions           │  - Business logic                   │
│  - Validation schemas         │  - Domain operations                │
│  - Business rules             │  - External integrations            │
├─────────────────────────────────────────────────────────────────────┤
│                      Infrastructure Layer                           │
├─────────────────────────────────────────────────────────────────────┤
│  API Client                   │  State Management                   │
│  - HTTP communication         │  - React Query (server state)       │
│  - Request/Response handling  │  - Redux (client state)             │
│  - Interceptors               │  - Local storage                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Proposed File Structure
```
console/
├── src/
│   ├── features/               # Feature modules
│   │   ├── machines/
│   │   │   ├── components/     # Feature-specific components
│   │   │   │   ├── MachineList.tsx
│   │   │   │   ├── MachineForm.tsx
│   │   │   │   └── MachineActions.tsx
│   │   │   ├── hooks/          # Feature-specific hooks
│   │   │   │   ├── useMachines.ts
│   │   │   │   ├── useMachineActions.ts
│   │   │   │   └── useMachineForm.ts
│   │   │   ├── services/       # Feature-specific services
│   │   │   │   └── machineService.ts
│   │   │   ├── models/         # Feature-specific models
│   │   │   │   └── machine.types.ts
│   │   │   ├── controllers/    # Business logic controllers
│   │   │   │   └── machineController.ts
│   │   │   └── index.ts        # Public API
│   │   ├── repositories/
│   │   ├── teams/
│   │   ├── queue/
│   │   └── auth/
│   ├── shared/                 # Shared across features
│   │   ├── components/         # Shared UI components
│   │   ├── hooks/              # Shared hooks
│   │   ├── services/           # Shared services
│   │   ├── models/             # Shared models
│   │   └── utils/              # Shared utilities
│   ├── core/                   # Core framework setup
│   │   ├── api/                # API client configuration
│   │   ├── store/              # Redux configuration
│   │   ├── query/              # React Query configuration
│   │   └── router/             # Router configuration
│   └── pages/                  # Page compositions
│       ├── ResourcesPage/
│       │   ├── ResourcesPage.tsx
│       │   ├── MachinesTab.tsx
│       │   ├── RepositoriesTab.tsx
│       │   └── index.ts
│       └── DashboardPage/
```

## Implementation Details

### 1. Feature Module Structure

Each feature module is self-contained with its own:

```typescript
// features/machines/index.ts - Public API
export { MachineList } from './components/MachineList';
export { useMachines, useMachineActions } from './hooks';
export { machineService } from './services';
export type { Machine, MachineFormData } from './models';
```

### 2. Models Layer

Type-safe domain models with validation:

```typescript
// features/machines/models/machine.types.ts
import { z } from 'zod';

// Zod schema for validation
export const MachineSchema = z.object({
  machineId: z.number(),
  machineName: z.string().min(1),
  teamName: z.string(),
  vaultData: z.record(z.unknown()).optional(),
  isActive: z.boolean(),
  tags: z.array(z.string()),
  createdDate: z.string(),
  lastModifiedDate: z.string()
});

// TypeScript types
export type Machine = z.infer<typeof MachineSchema>;

export interface MachineFormData {
  machineName: string;
  teamName: string;
  tags: string[];
  vaultData?: Record<string, unknown>;
}

// Domain rules
export const MachineRules = {
  isValidName: (name: string) => /^[a-zA-Z0-9-_]+$/.test(name),
  canDelete: (machine: Machine) => machine.isActive === false,
  requiresVault: (machine: Machine) => machine.tags.includes('secure')
};
```

### 3. Services Layer

Business logic and external integrations:

```typescript
// features/machines/services/machineService.ts
import { apiClient } from '@/core/api';
import { Machine, MachineFormData, MachineSchema } from '../models';
import { encryptVault } from '@/shared/services/encryption';

export class MachineService {
  async getMachines(teamName: string): Promise<Machine[]> {
    const response = await apiClient.post('/GetMachines', { teamName });
    return z.array(MachineSchema).parse(response.data);
  }

  async createMachine(data: MachineFormData): Promise<Machine> {
    const payload = {
      ...data,
      vaultData: data.vaultData 
        ? await encryptVault(data.vaultData) 
        : undefined
    };
    
    const response = await apiClient.post('/CreateMachine', payload);
    return MachineSchema.parse(response.data);
  }

  async deleteMachine(machineId: number): Promise<void> {
    await apiClient.post('/DeleteMachine', { machineId });
  }

  async testConnection(machine: Machine): Promise<boolean> {
    const response = await apiClient.post('/TestMachineConnection', {
      machineId: machine.machineId
    });
    return response.data.success;
  }
}

export const machineService = new MachineService();
```

### 4. Controllers Layer

Complex business operations and orchestration:

```typescript
// features/machines/controllers/machineController.ts
import { machineService } from '../services';
import { queueService } from '@/features/queue/services';
import { Machine, MachineRules } from '../models';

export class MachineController {
  async deployToMachine(
    machine: Machine,
    repositoryId: number,
    version: string
  ): Promise<void> {
    // Validate business rules
    if (!machine.isActive) {
      throw new Error('Cannot deploy to inactive machine');
    }

    // Build queue vault
    const queueVault = {
      function: 'deploy',
      parameters: {
        repositoryId,
        version,
        machineId: machine.machineId
      }
    };

    // Create queue item with proper priority
    await queueService.createQueueItem({
      teamName: machine.teamName,
      machineName: machine.machineName,
      queueVault,
      priority: version === 'latest' ? 2 : 3
    });
  }

  async bulkUpdateMachines(
    teamName: string,
    updates: Partial<Machine>
  ): Promise<void> {
    const machines = await machineService.getMachines(teamName);
    
    // Use Promise.allSettled for partial failure handling
    const results = await Promise.allSettled(
      machines.map(machine => 
        machineService.updateMachine(machine.machineId, updates)
      )
    );

    const failures = results.filter(r => r.status === 'rejected');
    if (failures.length > 0) {
      throw new Error(`Failed to update ${failures.length} machines`);
    }
  }
}

export const machineController = new MachineController();
```

### 5. Hooks Layer

State management and effect handling:

```typescript
// features/machines/hooks/useMachines.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { machineService } from '../services';
import { useTeamContext } from '@/shared/hooks/useTeamContext';

export function useMachines() {
  const { selectedTeam } = useTeamContext();
  
  const query = useQuery({
    queryKey: ['machines', selectedTeam],
    queryFn: () => machineService.getMachines(selectedTeam),
    enabled: !!selectedTeam,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  return {
    machines: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch
  };
}

// features/machines/hooks/useMachineActions.ts
export function useMachineActions() {
  const queryClient = useQueryClient();
  const { selectedTeam } = useTeamContext();

  const createMutation = useMutation({
    mutationFn: machineService.createMachine,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['machines', selectedTeam] });
      toast.success('Machine created successfully');
    },
    onError: (error) => {
      toast.error(`Failed to create machine: ${error.message}`);
    }
  });

  const deleteMutation = useMutation({
    mutationFn: machineService.deleteMachine,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['machines', selectedTeam] });
    }
  });

  return {
    createMachine: createMutation.mutate,
    deleteMachine: deleteMutation.mutate,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending
  };
}

// features/machines/hooks/useMachineForm.ts
export function useMachineForm(onSuccess?: () => void) {
  const { createMachine } = useMachineActions();
  
  const form = useForm<MachineFormData>({
    resolver: zodResolver(MachineFormSchema),
    defaultValues: {
      machineName: '',
      teamName: '',
      tags: []
    }
  });

  const handleSubmit = form.handleSubmit(async (data) => {
    await createMachine(data, {
      onSuccess: () => {
        form.reset();
        onSuccess?.();
      }
    });
  });

  return {
    form,
    handleSubmit,
    isSubmitting: form.formState.isSubmitting
  };
}
```

### 6. Components Layer

Pure presentational components:

```typescript
// features/machines/components/MachineList.tsx
import { Machine } from '../models';
import { MachineActions } from './MachineActions';

interface MachineListProps {
  machines: Machine[];
  isLoading: boolean;
  onMachineSelect: (machine: Machine) => void;
  onMachineDelete: (machine: Machine) => void;
}

export function MachineList({
  machines,
  isLoading,
  onMachineSelect,
  onMachineDelete
}: MachineListProps) {
  if (isLoading) {
    return <Skeleton active />;
  }

  return (
    <Table
      dataSource={machines}
      rowKey="machineId"
      columns={[
        {
          title: 'Name',
          dataIndex: 'machineName',
          render: (name, machine) => (
            <Button type="link" onClick={() => onMachineSelect(machine)}>
              {name}
            </Button>
          )
        },
        {
          title: 'Status',
          dataIndex: 'isActive',
          render: (isActive) => (
            <Tag color={isActive ? 'green' : 'red'}>
              {isActive ? 'Active' : 'Inactive'}
            </Tag>
          )
        },
        {
          title: 'Actions',
          render: (_, machine) => (
            <MachineActions
              machine={machine}
              onDelete={() => onMachineDelete(machine)}
            />
          )
        }
      ]}
    />
  );
}

// features/machines/components/MachineActions.tsx
interface MachineActionsProps {
  machine: Machine;
  onDelete: () => void;
}

export function MachineActions({ machine, onDelete }: MachineActionsProps) {
  const { t } = useTranslation();
  const { canDelete } = MachineRules;

  const actions = [
    {
      key: 'connect',
      label: t('machines.actions.connect'),
      onClick: () => {/* ... */}
    },
    {
      key: 'edit',
      label: t('machines.actions.edit'),
      onClick: () => {/* ... */}
    },
    {
      key: 'delete',
      label: t('machines.actions.delete'),
      danger: true,
      disabled: !canDelete(machine),
      onClick: onDelete
    }
  ];

  return (
    <Dropdown menu={{ items: actions }}>
      <Button icon={<MoreOutlined />} />
    </Dropdown>
  );
}
```

### 7. Page Composition

Pages compose features together:

```typescript
// pages/ResourcesPage/MachinesTab.tsx
import { useMachines, useMachineActions } from '@/features/machines';
import { MachineList } from '@/features/machines/components';

export function MachinesTab() {
  const { machines, isLoading, refetch } = useMachines();
  const { deleteMachine } = useMachineActions();
  const [showCreateModal, setShowCreateModal] = useState(false);

  return (
    <div className="machines-tab">
      <div className="machines-tab__header">
        <Button 
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setShowCreateModal(true)}
        >
          Create Machine
        </Button>
        <Button onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      <MachineList
        machines={machines}
        isLoading={isLoading}
        onMachineSelect={(machine) => {/* ... */}}
        onMachineDelete={(machine) => {
          Modal.confirm({
            title: 'Delete Machine',
            content: `Are you sure you want to delete ${machine.machineName}?`,
            onOk: () => deleteMachine(machine.machineId)
          });
        }}
      />

      <CreateMachineModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
      />
    </div>
  );
}

// pages/ResourcesPage/ResourcesPage.tsx
export function ResourcesPage() {
  const [activeTab, setActiveTab] = useState('machines');

  const items = [
    {
      key: 'machines',
      label: 'Machines',
      children: <MachinesTab />
    },
    {
      key: 'repositories',
      label: 'Repositories',
      children: <RepositoriesTab />
    },
    // ... other tabs
  ];

  return (
    <PageContainer>
      <Tabs 
        activeKey={activeTab}
        onChange={setActiveTab}
        items={items}
      />
    </PageContainer>
  );
}
```

## Migration Strategy

### Phase 1: Foundation Setup (Week 1-2)
1. **Create Core Infrastructure**
   - Set up feature module structure
   - Create shared components library
   - Implement base hooks and utilities
   - Set up testing infrastructure

2. **Establish Patterns**
   - Create example feature module
   - Document coding standards
   - Set up linting rules
   - Create component templates

### Phase 2: Extract Services (Week 2-3)
1. **Identify Business Logic**
   - Extract queue creation logic
   - Extract vault building logic
   - Extract validation logic

2. **Create Service Layer**
   - Implement resource services
   - Create queue service
   - Build encryption service
   - Add error handling

### Phase 3: Feature Migration (Week 3-6)
1. **Machines Feature**
   - Extract from ResourcesPage
   - Create dedicated components
   - Implement hooks
   - Add tests

2. **Repositories Feature**
   - Similar extraction process
   - Reuse patterns from machines

3. **Teams Feature**
   - Extract team management
   - Implement team context

4. **Queue Feature**
   - Consolidate queue logic
   - Create queue monitoring hooks
   - Build queue components

### Phase 4: Component Refactoring (Week 6-8)
1. **Break Down Large Components**
   - Split ResourcesPage into tabs
   - Extract form components
   - Create action menus

2. **Implement Lazy Loading**
   - Code split by route
   - Lazy load heavy components
   - Optimize bundle size

### Phase 5: State Management (Week 8-9)
1. **Standardize Patterns**
   - React Query for all server state
   - Redux for auth and UI only
   - Local state for forms

2. **Remove State Duplication**
   - Consolidate overlapping state
   - Use single source of truth
   - Implement proper caching

### Phase 6: Testing and Documentation (Week 9-10)
1. **Comprehensive Testing**
   - Unit tests for services
   - Integration tests for hooks
   - Component tests
   - E2E tests for critical paths

2. **Documentation**
   - Architecture guide
   - Component library
   - Best practices
   - Migration guide

## Code Examples

### Example 1: Current vs New Resource Management

**Current Implementation** (monolithic):
```typescript
// pages/ResourcesPage.tsx - 1900+ lines
function ResourcesPage() {
  const [activeTab, setActiveTab] = useState('machines');
  const [machines, setMachines] = useState([]);
  const [repositories, setRepositories] = useState([]);
  const [loading, setLoading] = useState(false);
  // ... more state

  // Fetching logic mixed with UI
  const fetchMachines = async () => {
    setLoading(true);
    try {
      const response = await apiClient.post('/GetMachines', { 
        teamName: selectedTeam 
      });
      setMachines(response.data);
    } catch (error) {
      message.error('Failed to fetch machines');
    } finally {
      setLoading(false);
    }
  };

  // Business logic in component
  const createQueueItem = async (machine, repo, functionName) => {
    const vaultData = {
      function: functionName,
      parameters: {
        machineId: machine.id,
        repositoryId: repo.id
      }
    };
    
    const encrypted = await encryptVault(vaultData);
    await apiClient.post('/CreateQueueItem', {
      teamName: selectedTeam,
      machineName: machine.name,
      queueVault: encrypted
    });
  };

  // Massive render method
  return (
    <div>
      {/* 1000+ lines of JSX */}
    </div>
  );
}
```

**New Implementation** (modular):

```typescript
// features/machines/hooks/useMachines.ts
export function useMachines() {
  const { selectedTeam } = useTeamContext();
  
  return useQuery({
    queryKey: ['machines', selectedTeam],
    queryFn: () => machineService.getMachines(selectedTeam),
    enabled: !!selectedTeam
  });
}

// features/queue/services/queueService.ts
export class QueueService {
  async createQueueItem(params: CreateQueueParams): Promise<QueueItem> {
    const vaultData = this.buildQueueVault(params);
    const encrypted = await encryptionService.encryptVault(vaultData);
    
    return apiClient.post('/CreateQueueItem', {
      teamName: params.teamName,
      machineName: params.machineName,
      queueVault: encrypted,
      priority: params.priority ?? 3
    });
  }

  private buildQueueVault(params: CreateQueueParams): QueueVault {
    return {
      function: params.functionName,
      parameters: params.parameters,
      metadata: {
        createdAt: new Date().toISOString(),
        createdBy: getCurrentUser().id
      }
    };
  }
}

// pages/ResourcesPage/MachinesTab.tsx
export function MachinesTab() {
  const { machines, isLoading } = useMachines();
  const { createQueueItem } = useQueueActions();

  const handleDeploy = async (machine: Machine, repo: Repository) => {
    await createQueueItem({
      teamName: machine.teamName,
      machineName: machine.machineName,
      functionName: 'deploy',
      parameters: {
        machineId: machine.id,
        repositoryId: repo.id
      }
    });
  };

  return (
    <MachineList
      machines={machines}
      isLoading={isLoading}
      onDeploy={handleDeploy}
    />
  );
}
```

### Example 2: Testing with New Architecture

```typescript
// features/machines/services/__tests__/machineService.test.ts
describe('MachineService', () => {
  let service: MachineService;
  let mockApiClient: jest.Mocked<typeof apiClient>;

  beforeEach(() => {
    mockApiClient = apiClient as jest.Mocked<typeof apiClient>;
    service = new MachineService();
  });

  describe('getMachines', () => {
    it('should fetch and parse machines correctly', async () => {
      const mockResponse = {
        data: [
          { machineId: 1, machineName: 'prod-01', isActive: true }
        ]
      };

      mockApiClient.post.mockResolvedValue(mockResponse);

      const machines = await service.getMachines('team1');

      expect(mockApiClient.post).toHaveBeenCalledWith('/GetMachines', {
        teamName: 'team1'
      });
      expect(machines).toHaveLength(1);
      expect(machines[0].machineName).toBe('prod-01');
    });

    it('should handle API errors gracefully', async () => {
      mockApiClient.post.mockRejectedValue(new Error('Network error'));

      await expect(service.getMachines('team1')).rejects.toThrow('Network error');
    });
  });
});

// features/machines/hooks/__tests__/useMachines.test.tsx
describe('useMachines', () => {
  it('should fetch machines when team is selected', async () => {
    const mockMachines = [
      { machineId: 1, machineName: 'prod-01' }
    ];

    jest.spyOn(machineService, 'getMachines')
      .mockResolvedValue(mockMachines);

    const { result } = renderHook(() => useMachines(), {
      wrapper: createWrapper({
        teamContext: { selectedTeam: 'team1' }
      })
    });

    await waitFor(() => {
      expect(result.current.machines).toEqual(mockMachines);
    });
  });
});
```

## Testing Strategy

### 1. Unit Tests

**Services**: Test business logic in isolation
```typescript
// Pure functions, easy to test
expect(machineService.validateMachineName('prod-01')).toBe(true);
expect(machineService.validateMachineName('prod 01')).toBe(false);
```

**Hooks**: Test state management and effects
```typescript
// Test React Query integration
const { result } = renderHook(() => useMachines());
await waitFor(() => expect(result.current.isLoading).toBe(false));
```

**Components**: Test rendering and user interactions
```typescript
// Test pure UI components
render(<MachineList machines={mockMachines} />);
expect(screen.getByText('prod-01')).toBeInTheDocument();
```

### 2. Integration Tests

**Feature Integration**: Test complete features
```typescript
// Test machine creation flow
const user = userEvent.setup();
render(<MachineFeature />);

await user.click(screen.getByText('Create Machine'));
await user.type(screen.getByLabelText('Name'), 'new-machine');
await user.click(screen.getByText('Submit'));

await waitFor(() => {
  expect(screen.getByText('new-machine')).toBeInTheDocument();
});
```

### 3. E2E Tests

**Critical User Journeys**: Test complete workflows
```typescript
// Test deploy to production flow
test('deploy to production', async ({ page }) => {
  await page.goto('/resources');
  await page.click('text=Machines');
  await page.click('text=prod-01');
  await page.click('text=Deploy');
  await page.selectOption('select[name=repository]', 'main-app');
  await page.click('text=Deploy Now');
  
  await expect(page.locator('.notification')).toContainText('Deployment started');
});
```

## Best Practices

### 1. Feature Module Guidelines

**Public API**: Each feature exports only what's needed
```typescript
// features/machines/index.ts
// ✅ Good - Controlled exports
export { MachineList, MachineForm } from './components';
export { useMachines, useMachineActions } from './hooks';
export type { Machine } from './models';

// ❌ Bad - Exposing internals
export * from './components';
export * from './services/internal';
```

**Dependency Direction**: Features depend on shared, not on each other
```typescript
// ✅ Good
import { useAuth } from '@/shared/hooks/useAuth';
import { Button } from '@/shared/components';

// ❌ Bad - Cross-feature dependency
import { RepositoryList } from '@/features/repositories';
```

### 2. State Management Principles

**Single Source of Truth**: Each piece of state has one owner
```typescript
// ✅ Good - Server state in React Query
const { data: machines } = useQuery(['machines', team], fetchMachines);

// ❌ Bad - Duplicating server state in Redux
dispatch(setMachines(fetchedMachines));
```

**Proper State Location**: Put state where it's needed
```typescript
// ✅ Good - Form state local to form
function MachineForm() {
  const [formData, setFormData] = useState({});
}

// ❌ Bad - Form state in global store
const formData = useSelector(state => state.machines.formData);
```

### 3. Component Design Principles

**Separation of Concerns**: Components should have a single responsibility
```typescript
// ✅ Good - Presentational component
function MachineCard({ machine, onEdit, onDelete }) {
  return (
    <Card>
      <h3>{machine.name}</h3>
      <Button onClick={() => onEdit(machine)}>Edit</Button>
      <Button onClick={() => onDelete(machine)}>Delete</Button>
    </Card>
  );
}

// ❌ Bad - Mixed concerns
function MachineCard({ machineId }) {
  const machine = useSelector(state => state.machines[machineId]);
  const dispatch = useDispatch();
  
  const handleDelete = async () => {
    await apiClient.delete(`/machines/${machineId}`);
    dispatch(removeMachine(machineId));
  };
  
  return (/* ... */);
}
```

### 4. Error Handling

**Graceful Degradation**: Handle errors at appropriate levels
```typescript
// Service level - Throw specific errors
class MachineService {
  async createMachine(data: MachineFormData) {
    try {
      return await apiClient.post('/CreateMachine', data);
    } catch (error) {
      if (error.response?.status === 409) {
        throw new MachineExistsError(data.machineName);
      }
      throw new ServiceError('Failed to create machine', error);
    }
  }
}

// Hook level - Transform to UI-friendly errors
function useMachineActions() {
  const mutation = useMutation({
    mutationFn: machineService.createMachine,
    onError: (error) => {
      if (error instanceof MachineExistsError) {
        toast.error(`Machine ${error.machineName} already exists`);
      } else {
        toast.error('Failed to create machine. Please try again.');
      }
    }
  });
}
```

### 5. Performance Optimization

**Code Splitting**: Load features on demand
```typescript
// Router configuration
const routes = [
  {
    path: '/resources',
    element: <ResourcesLayout />,
    children: [
      {
        path: 'machines',
        lazy: () => import('@/features/machines/pages/MachinesPage')
      },
      {
        path: 'repositories',
        lazy: () => import('@/features/repositories/pages/RepositoriesPage')
      }
    ]
  }
];
```

**Memoization**: Optimize expensive computations
```typescript
// Use React.memo for pure components
export const MachineList = React.memo(({ machines, onSelect }) => {
  return (/* ... */);
});

// Use useMemo for expensive calculations
const sortedMachines = useMemo(
  () => machines.sort((a, b) => a.name.localeCompare(b.name)),
  [machines]
);
```

## Implementation Checklist

### Phase 1: Foundation
- [ ] Create feature folder structure
- [ ] Set up shared components library
- [ ] Implement base hooks
- [ ] Configure testing framework
- [ ] Create coding standards document

### Phase 2: Services
- [ ] Extract machine service
- [ ] Extract repository service
- [ ] Extract queue service
- [ ] Implement encryption service
- [ ] Add comprehensive error handling

### Phase 3: Feature Migration
- [ ] Migrate machines feature
- [ ] Migrate repositories feature
- [ ] Migrate teams feature
- [ ] Migrate queue feature
- [ ] Migrate bridges feature

### Phase 4: Components
- [ ] Break down ResourcesPage
- [ ] Create reusable form components
- [ ] Implement action menus
- [ ] Add loading states
- [ ] Implement error boundaries

### Phase 5: State Management
- [ ] Migrate to React Query for all server state
- [ ] Remove Redux for server state
- [ ] Implement proper caching strategies
- [ ] Add optimistic updates
- [ ] Set up real-time updates

### Phase 6: Testing
- [ ] Unit tests for all services
- [ ] Integration tests for features
- [ ] Component tests
- [ ] E2E tests for critical paths
- [ ] Performance testing

## Conclusion

This modular architecture transformation will provide:

1. **Improved Maintainability**: Smaller, focused modules are easier to understand and modify
2. **Better Testing**: Isolated components and services can be tested independently
3. **Enhanced Developer Experience**: Clear patterns and structure make development faster
4. **Scalability**: New features can be added without affecting existing code
5. **Performance**: Code splitting and lazy loading improve initial load times
6. **Team Collaboration**: Features can be developed in parallel by different team members

The migration can be done incrementally, allowing for continuous delivery while maintaining stability. Each phase builds upon the previous one, ensuring a smooth transition from the current monolithic structure to a modern, modular architecture.