# Console Services

## Hello Service

The `helloService.ts` provides a standardized way to execute the `hello` function across the application. This service is used for connectivity testing and quick machine health checks.

### Usage

#### Using the Hook (Recommended for React Components)

```typescript
import { useHelloFunction } from '@/services/helloService';

function MyComponent() {
  const { executeHelloForMachine, isLoading } = useHelloFunction();
  
  const handleTestConnection = async (machine) => {
    const result = await executeHelloForMachine(machine, {
      priority: 1,
      description: 'Connection test',
      addedVia: 'my-component'
    });
    
    if (result.success) {
      console.log('Task created with ID:', result.taskId);
    } else {
      console.error('Failed:', result.error);
    }
  };
}
```

#### Using the Service Class (For Non-React Code)

```typescript
import { HelloService } from '@/services/helloService';

const result = await HelloService.executeHello({
  teamName: 'team1',
  machineName: 'machine1',
  bridgeName: 'bridge1',
  priority: 3,
  description: 'Test connection'
}, buildQueueVault, createQueueItem);
```

### Integration Points

The hello service is currently integrated in:
- **ConnectivityTestModal**: For bulk connectivity testing of machines
- **MachineTable**: Quick test connection option in the machine actions dropdown

### Benefits

1. **Consistency**: All hello function calls use the same logic
2. **Error Handling**: Centralized error handling and response formatting
3. **Type Safety**: Full TypeScript support with proper interfaces
4. **Reusability**: Easy to add hello functionality to any component
5. **Maintainability**: Single source of truth for hello function logic
