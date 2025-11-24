// Custom hooks for reducing code duplication

export { useUnifiedModal } from './useUnifiedModal'
export type { UnifiedModalState, UseUnifiedModalReturn } from './useUnifiedModal'

export { useTeamSelection } from './useTeamSelection'
export type { UseTeamSelectionOptions, UseTeamSelectionReturn } from './useTeamSelection'

export { usePagination, useMultiPagination } from './usePagination'
export type { UsePaginationOptions, UsePaginationReturn } from './usePagination'

// Dialog/Modal state management
export { useDialogState, useTraceModal, useQueueTraceModal } from './useDialogState'
export type {
  DialogState,
  UseDialogStateReturn,
  TraceModalData,
  QueueTraceModalState,
  UseQueueTraceModalReturn,
} from './useDialogState'

export { useFormModal, useExtendedFormModal } from './useFormModal'
export type {
  FormModalMode,
  FormModalState,
  UseFormModalReturn,
  ExtendedFormModalState,
  UseExtendedFormModalReturn,
} from './useFormModal'

// Filter state management
export { useFilters } from './useFilters'
export type { UseFiltersOptions, UseFiltersReturn, FilterValue } from './useFilters'

// Async action handling
export { useAsyncAction, executeMultiStep, useFormSubmission } from './useAsyncAction'
export type {
  AsyncActionResult,
  AsyncActionConfig,
  UseAsyncActionReturn,
  MultiStepActionConfig,
  UseFormSubmissionConfig,
  UseFormSubmissionReturn,
} from './useAsyncAction'

// Table state management
export { useExpandableTable } from './useExpandableTable'
export type { UseExpandableTableReturn } from './useExpandableTable'
