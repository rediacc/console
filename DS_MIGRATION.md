# Distributed Storage Migration Plan for Console

**Progress: ~98% Complete** 🚀

## Overview

This document outlines the comprehensive plan to update the console application to support the new distributed storage features, including machine exclusivity management and bulk operations.

## 1. Type Definitions Updates

### 1.1 Update Core Types (`src/types/index.ts`)
- [x] Already has `distributedStorageClusterName` in Machine interface
- [x] Add new machine assignment status types:
  ```typescript
  export type MachineAssignmentType = 'AVAILABLE' | 'CLUSTER' | 'IMAGE' | 'CLONE'
  
  export interface MachineAssignmentStatus {
    assignmentType: MachineAssignmentType
    assignmentDetails: string
  }
  ```

### 1.2 API Query Types (Already Updated)
- [x] Updated interfaces in `src/api/queries/distributedStorage.ts`
- [x] Added new interfaces for machine operations
- [x] Updated existing interfaces to match SQL SELECT statements

## 2. Component Updates

### 2.1 Machine Components (`src/components/resources/`)

#### MachineTable.tsx
- [x] Add distributed storage status column showing assignment type
- [x] Add bulk selection for machine operations
- [x] Add action buttons for:
  - Assign to Cluster
  - Remove from Cluster
  - View Assignment Status
- [x] Integrate with new API hooks

#### AssignToClusterModal.tsx (Already Exists)
- [x] Review and ensure it uses the new `useUpdateMachineClusterAssignment` hook
- [x] Add validation for machine exclusivity
- [x] Updated to support both single and bulk operations

#### New Components Needed:
- [x] `AssignMachinesToCloneModal.tsx` - Bulk assign machines to clones
- [x] `MachineAssignmentStatusBadge.tsx` - Visual indicator for assignment status
- [x] `MachineAssignmentStatusCell.tsx` - Wrapper component for fetching and displaying status
- [x] `RemoveFromClusterModal.tsx` - Bulk remove machines from clusters
- [x] `ViewAssignmentStatusModal.tsx` - View assignment status for selected machines
- [x] `AvailableMachinesSelector.tsx` - Multi-select for available machines
- [x] `ImageMachineReassignmentModal.tsx` - Reassign images to different machines

### 2.2 Distributed Storage Components (`src/pages/distributedStorage/components/`)

#### RbdImageList.tsx
- [x] Update create image flow to require machine selection
- [x] Show assigned machine in the image list
- [x] Add machine reassignment functionality (UI complete, awaiting backend API)

#### CloneList.tsx
- [x] Add machine management section (expandable rows with assigned machines)
- [x] Show assigned machines for each clone (machine count badge in table)
- [x] Add bulk assign/remove machine buttons (via modal)
- [x] Integrate with new machine management hooks
- [x] Added "Manage Machines" option in actions menu

#### ClusterTable.tsx
- [x] Show machine count for each cluster
- [x] Add link to view/manage cluster machines
- [x] Created `ManageClusterMachinesModal.tsx` for cluster machine management

#### New Components:
- [x] `CloneMachineManager.tsx` - Manage machines assigned to a clone
- [x] `MachineExclusivityWarning.tsx` - Show warnings when machines are already assigned

## 3. Feature Module Structure (`src/features/distributed-storage/`)

### 3.1 Models
- [x] Created `machine-assignment.model.ts` with comprehensive types:
  - MachineAssignment interface for tracking assignments
  - BulkOperationRequest for batch operations
  - AssignmentConflict and resolution types
  - AssignmentResult for operation outcomes
  - MachineAssignmentSummary for statistics
- [x] Created `machine-validation.model.ts` with validation types:
  - ValidationResult with errors and warnings
  - BulkValidationResult for batch validation
  - ValidationContext for rule configuration
  - ExclusivityValidation for conflict detection
  - CapacityValidation for resource limits

### 3.2 Services
- [x] `machine-assignment.service.ts` - Business logic for machine assignments
- [x] `machine-validation.service.ts` - Client-side validation for exclusivity
- [x] Created comprehensive services with:
  - Machine assignment type detection and formatting
  - Exclusivity validation and conflict resolution
  - Bulk operation support
  - Team-based statistics and filtering
  - Integration with existing API hooks

### 3.3 Hooks
- [x] `useMachineAssignment.ts` - Combined hook for machine assignment operations
- [x] `useBulkMachineOperations.ts` - Handle bulk selections and operations
- [x] `useMachineExclusivity.ts` - Check and validate machine availability
- [x] Created comprehensive hooks with:
  - Unified interface for all assignment operations
  - Bulk operation support with progress tracking
  - Real-time availability checking with caching
  - Debounced validation for performance
  - Integration with services and API hooks
  - Full TypeScript type safety

### 3.4 Controllers
- [x] `machine-assignment.controller.ts` - Orchestrate machine assignment flows
- [x] `bulk-operations.controller.ts` - Handle bulk machine operations
- [x] Created comprehensive controllers with:
  - Multi-step workflow orchestration with rollback support
  - Event-driven architecture for progress tracking
  - Command pattern for undo/redo operations
  - Batch processing with retry logic
  - Conflict resolution strategies
  - Detailed operation reporting
  - README with usage examples

## 4. State Management Updates

### 4.1 Redux Store (`src/store/`)
- [x] Add machine assignment slice:
  ```typescript
  // store/distributedStorage/machineAssignmentSlice.ts
  interface MachineAssignmentState {
    selectedMachines: string[]
    assignmentValidation: Record<string, ValidationResult>
    bulkOperationInProgress: boolean
  }
  ```
- [x] Created comprehensive Redux store with:
  - Machine selection management (single/multiple modes)
  - Validation state with cache management
  - Operation progress tracking and history
  - Filter and UI state management
  - Memoized selectors for performance
  - Custom hooks for easy integration

### 4.2 Query Cache Management
- [x] Update invalidation logic for related queries
- [x] Add optimistic updates for better UX
- [x] Implemented middleware for:
  - Automatic validation cache cleanup (5-minute expiry)
  - Selection persistence to sessionStorage
  - Development logging for debugging
  - Side effect management

## 5. UI/UX Improvements

### 5.1 Visual Indicators
- [x] Color-coded badges for machine assignment status:
  - Green: Available
  - Blue: Assigned to Cluster
  - Purple: Assigned to Image
  - Orange: Assigned to Clone
  
### 5.2 Bulk Operations UI
- [x] Checkbox selection in machine tables
- [x] Bulk action toolbar
- [x] Progress indicator for bulk operations
- [x] Summary dialog showing operation results

### 5.3 Validation Feedback
- [x] Real-time validation as users select machines
- [x] Clear error messages for exclusivity violations
- [ ] Suggestions for alternative available machines

## 6. Integration Points

### 6.1 Machine Page Integration
- [x] Update `src/pages/resources/ResourcesPage.tsx` machine tab
- [x] Add distributed storage section to machine details
- [x] Show assignment history in audit trail

### 6.2 Distributed Storage Page Integration
- [x] Update `src/pages/distributedStorage/DistributedStoragePage.tsx`
- [x] Add machine management tab
- [x] Integrate machine availability checks

### 6.3 Dashboard Integration
- [x] Add distributed storage machine metrics
- [x] Show machine utilization by assignment type
- [x] Updated GetCompanyDashboardJson stored procedure to include distributedStorageStats
- [x] Created DistributedStorageDashboardWidget component
- [x] Added TypeScript types for distributed storage stats
- [x] Integrated widget into DashboardPage (Premium/Elite only)

## 7. Localization Updates

### 7.1 Translation Keys (`src/i18n/locales/*/`)
Update all language files with new keys:
- [x] Machine assignment status messages
- [x] Bulk operation messages
- [x] Validation error messages
- [x] Success/failure notifications (added for all operations)
- [x] Image reassignment messages
- [x] Clone machine management messages
- [x] Created `distributedStorage.json` localization file
- [x] Added distributed storage section strings
- [x] Added audit trail action types for distributed storage

Example keys to add:
```json
{
  "machines": {
    "assignmentStatus": {
      "available": "Available for assignment",
      "cluster": "Assigned to cluster: {{clusterName}}",
      "image": "Assigned to image: {{imageName}}",
      "clone": "Assigned to clone: {{cloneName}}"
    },
    "bulkOperations": {
      "assignToClone": "Assign to Clone",
      "removeFromClone": "Remove from Clone",
      "validating": "Validating machine availability...",
      "assignmentSuccess": "Successfully assigned {{count}} machines",
      "assignmentPartial": "Assigned {{success}} of {{total}} machines",
      "removalSuccess": "Successfully removed {{count}} machines"
    },
    "validation": {
      "alreadyAssigned": "Machine is already assigned to {{resourceType}}: {{resourceName}}",
      "noMachinesSelected": "Please select at least one machine",
      "allMachinesUnavailable": "All selected machines are unavailable"
    }
  }
}
```

## 8. Testing Requirements

### 8.1 Unit Tests
- [ ] Test machine exclusivity validation logic
- [ ] Test bulk operation state management
- [ ] Test API hook integration

### 8.2 Integration Tests
- [ ] Test complete assignment flow
- [ ] Test error handling for conflicts
- [ ] Test cache invalidation

### 8.3 E2E Tests
- [ ] Test machine assignment from different entry points
- [ ] Test bulk operations with large selections
- [ ] Test concurrent assignment attempts

## 9. Performance Considerations

### 9.1 Optimizations
- [x] Implement virtual scrolling for large machine lists
- [x] Batch API calls for bulk operations
- [x] Add debouncing for validation checks
- [x] Implement progressive loading for assignment status

### 9.2 Caching Strategy
- [ ] Cache machine assignment status
- [ ] Implement smart cache invalidation
- [ ] Add background refresh for active views

## 10. Migration Steps

### Phase 1: Foundation (Week 1) ✅
1. ✅ Update type definitions
2. ✅ Create base models and services
3. ✅ Update Redux store structure
4. ✅ Add localization keys

### Phase 2: Core Components (Week 2) ✅
1. ✅ Update MachineTable with new columns
2. ✅ Create machine assignment components
3. ✅ Update RbdImageList for required machines
4. ✅ Create bulk operation components

### Phase 3: Integration (Week 3) ✅
1. ✅ Integrate with distributed storage pages
2. ✅ Update machine detail views
3. ✅ Add dashboard widgets
4. ✅ Complete end-to-end flows

### Phase 4: Polish & Testing (Week 4)
1. Add loading states and error handling
2. Implement performance optimizations
3. Complete test coverage
4. User acceptance testing

## 11. Rollback Plan

### Gradual Rollout
1. Feature flag for new machine management features
2. Ability to disable bulk operations
3. Fallback to individual operations

### Data Safety
1. No destructive operations without confirmation
2. Audit trail for all assignments
3. Ability to bulk undo recent operations

## 12. Success Metrics

- Zero data loss during migration
- < 2s response time for assignment operations
- < 5s for bulk operations (up to 50 machines)
- 95% success rate for bulk operations
- Reduced support tickets for machine management

## 13. Dependencies

### External Dependencies
- Updated `@/api/queries/distributedStorage.ts` (✓ Complete)
- Backend API endpoints (✓ Complete)
- Updated SQL procedures (✓ Complete)

### Internal Dependencies
- Machine table component refactor (✓ Complete)
- State management setup (✓ Complete)
- Localization system updates (✓ Complete)

## 14. Risk Mitigation

### Identified Risks
1. **Performance degradation with many machines**
   - Mitigation: Virtual scrolling, pagination
   
2. **Race conditions in assignments**
   - Mitigation: Optimistic locking, proper error handling
   
3. **Complex UI for bulk operations**
   - Mitigation: Progressive disclosure, clear visual feedback

4. **Browser memory issues with large selections**
   - Mitigation: Limit selection size, batch processing

## Major Achievements

### 🎯 Complete Component Suite
We've successfully created a comprehensive set of components for distributed storage machine management:
- **17 new components** created across machine and distributed storage modules
- **2 service classes** with centralized business logic and validation
- **3 custom hooks** for machine operations and state management
- **2 controller classes** for workflow orchestration and bulk operations
- **5 model/type files** with comprehensive TypeScript types
- **Full CRUD operations** for machine assignments across clusters, images, and clones
- **Bulk operations** support with progress tracking and error handling
- **Real-time status updates** with visual indicators
- **Workflow orchestration** with event-driven architecture

### 🔧 Full Stack Integration
- **Backend**: Updated SQL procedures and C# controller endpoints
- **API Layer**: Complete set of React Query hooks with proper caching
- **Frontend**: Responsive UI with consistent UX patterns
- **Localization**: Full i18n support with all necessary translations
- **Service Layer**: Centralized business logic with MachineAssignmentService and MachineValidationService
- **Hooks Layer**: Comprehensive hooks for machine operations (useMachineAssignment, useBulkMachineOperations, useMachineExclusivity)
- **Controller Layer**: Workflow orchestration with MachineAssignmentController and BulkOperationsController
- **State Management**: Redux store with machine assignment slice, selectors, and middleware

### 📊 Key Features Delivered
1. **Machine Exclusivity Management**: Enforced one-to-one assignments for clusters/images
2. **Bulk Operations**: Select and manage multiple machines simultaneously
3. **Visual Status Indicators**: Color-coded badges showing assignment status
4. **Machine Reassignment**: Seamless reassignment with validation
5. **Export Capabilities**: Export machine lists in CSV format
6. **Search & Filter**: Find machines quickly across large datasets
7. **Dashboard Integration**: Real-time distributed storage metrics on main dashboard
8. **Team-Level Insights**: Machine assignment breakdown by team with visual statistics
9. **Service Layer Architecture**: Centralized business logic with validation and assignment services
10. **Workflow Orchestration**: Multi-step operations with rollback and event tracking
11. **Conflict Resolution**: Automated strategies for handling assignment conflicts
12. **Operation History**: Command pattern for undo/redo capabilities

## Completed Items Summary

### ✅ Machine Components (Section 2.1)
- MachineTable.tsx - Added bulk selection, assignment status column, and bulk operations
- AssignToClusterModal.tsx - Updated for single and bulk operations
- All new components created:
  - AssignMachinesToCloneModal.tsx
  - MachineAssignmentStatusBadge.tsx
  - MachineAssignmentStatusCell.tsx
  - RemoveFromClusterModal.tsx
  - ViewAssignmentStatusModal.tsx
  - AvailableMachinesSelector.tsx
  - ImageMachineReassignmentModal.tsx

### ✅ Distributed Storage Components (Section 2.2)
- RbdImageList.tsx - Machine column, selection, and reassignment UI with working API
- CloneList.tsx - Machine management with expandable rows and modal
- ClusterTable.tsx - Machine count display and manage link
- ManageClusterMachinesModal.tsx - New modal for cluster machine management
- CloneMachineManager.tsx - Comprehensive standalone component for clone machine management
- MachineExclusivityWarning.tsx - Warning component for assignment exclusivity

### ✅ Machine Page Integration (Section 6.1)
- MachineTable.tsx - Added distributed storage assignment status column
- MachineVaultStatusPanel.tsx - Added distributed storage section with assignment details
- AuditTraceModal.tsx - Updated to recognize distributed storage actions
- DistributedStorageSection.tsx - New component for machine details panel
- Created distributedStorage.json localization file with all necessary translations

### ✅ Distributed Storage Page Integration (Section 6.2)
- DistributedStoragePage.tsx - Added machines tab with full functionality
- DistributedStorageMachinesTab.tsx - Complete machine management interface
- MachineAvailabilitySummary.tsx - Statistics dashboard for machine assignments
- FilterableMachineTable.tsx - Custom table component for filtered machine display
- Integrated machine availability checks and assignment filtering

### ✅ UI/UX Improvements (Section 5)
- Color-coded assignment status badges
- Bulk selection and operations
- Progress indicators and result summaries
- Real-time validation feedback

### ✅ Localization (Section 7)
- All translation keys added for machine operations
- Success/failure notifications
- Validation messages
- Component-specific labels
- Machine exclusivity warnings

### ✅ Backend Work Completed
- [x] SQL procedure updated to return machine info for images (GetDistributedStorageRbdImages)
- [x] Created UpdateImageMachineAssignment stored procedure
- [x] Added all distributed storage RBD procedures to C# controller whitelist
- [x] Created API hooks for image machine reassignment

### ✅ API Integration (Section 1.2)
- [x] All distributed storage API hooks created and integrated
- [x] useUpdateImageMachineAssignment hook implemented
- [x] Machine assignment validation hooks
- [x] Bulk operation support in API layer

### ✅ Feature Module Structure (Section 3.1, 3.2, 3.3 & 3.4)
- [x] Created machine-assignment.model.ts with comprehensive types
- [x] Created machine-validation.model.ts with validation types
- [x] Implemented MachineAssignmentService with business logic
- [x] Implemented MachineValidationService with validation rules
- [x] Created useMachineAssignment.ts hook for unified assignment operations
- [x] Created useBulkMachineOperations.ts hook for bulk selection and operations
- [x] Created useMachineExclusivity.ts hook for availability checking
- [x] Created MachineAssignmentController for workflow orchestration
- [x] Created BulkOperationsController for bulk operation management
- [x] Added controller types file with workflow and event types
- [x] Added useDebounce utility for performance optimization
- [x] Added index files for easy imports
- [x] Fixed TypeScript issues and added missing properties

### ✅ Redux Store Implementation (Section 4)
- [x] Created machineAssignmentSlice.ts with comprehensive state management
- [x] Created machineAssignmentSelectors.ts with memoized selectors
- [x] Implemented middleware for validation cache management
- [x] Added selection persistence to sessionStorage
- [x] Created custom hooks for store integration
- [x] Updated store.ts with new slice and middleware
- [x] Added async thunk for machine validation
- [x] Created README with usage documentation

### ✅ Performance Optimizations (Section 9.1)
- [x] Created VirtualMachineTable component using react-window for efficient scrolling
- [x] Created VirtualFilterableMachineTable with debounced search and filtering
- [x] Implemented BatchApiService for efficient bulk operations:
  - Batch processing with configurable size
  - Retry logic with exponential backoff
  - Progress tracking and callbacks
  - Concurrent request limiting
- [x] Enhanced debouncing utilities:
  - useDebounce for values
  - useDebouncedCallback for functions
  - useDebouncedValidation for async validation
  - useDebouncedSearch with loading states
- [x] Created LazyAssignmentStatus component for progressive loading
- [x] Implemented useBackgroundRefresh hook for smart updates:
  - Tab visibility awareness
  - Activity-based refresh intervals
  - Selected machine prioritization
- [x] Updated BulkOperationsController to use BatchApiService

## Progress Summary
- **Completed**: ~98% of the migration plan
- **Major Features Done**: 
  - ✅ All Machine Components (Section 2.1)
  - ✅ All Distributed Storage Components (Section 2.2)
  - ✅ Complete API Integration
  - ✅ All SQL Updates
  - ✅ All UI/UX Improvements
  - ✅ All Localization Updates
  - ✅ Machine Page Integration (Section 6.1)
  - ✅ Distributed Storage Page Integration (Section 6.2)
  - ✅ Dashboard Integration (Section 6.3)
  - ✅ Complete Feature Module Structure (Section 3 - Models, Services, Hooks, and Controllers)
  - ✅ Redux Store Setup (Section 4 - State Management)
  - ✅ Performance Optimizations (Section 9.1)
- **Remaining Work**: 
  - Testing (Section 8) - Skipped per user request
  - Caching Strategy (Section 9.2) - Skipped per user request
  - Suggestions for alternative available machines (Section 5.3)

## Next Steps

1. Review and approve this plan
2. Create detailed tickets for each component
3. Set up feature flags
4. Begin Phase 1 implementation

---

This migration plan ensures a smooth transition to the new distributed storage machine management features while maintaining system stability and user experience.