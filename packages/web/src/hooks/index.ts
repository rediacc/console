// Custom hooks for reducing code duplication

export type {
  AsyncActionConfig,
  AsyncActionResult,
  MultiStepActionConfig,
  UseAsyncActionReturn,
  UseFormSubmissionConfig,
  UseFormSubmissionReturn,
} from './useAsyncAction';
// Async action handling
export { executeMultiStep, useAsyncAction, useFormSubmission } from './useAsyncAction';
// Confirmation dialog hook
export { useConfirmDialog } from './useConfirmDialog';
export type {
  DialogState,
  QueueTraceModalState,
  TraceModalData,
  UseDialogStateReturn,
  UseQueueTraceModalReturn,
} from './useDialogState';
// Dialog/Modal state management
export { useDialogState, useQueueTraceModal, useTraceModal } from './useDialogState';
export type { UseExpandableTableReturn } from './useExpandableTable';
// Table state management
export { useExpandableTable } from './useExpandableTable';
export type { FilterValue, UseFiltersOptions, UseFiltersReturn } from './useFilters';
// Filter state management
export { useFilters } from './useFilters';
export type {
  ExtendedFormModalState,
  FormModalMode,
  FormModalState,
  UseExtendedFormModalReturn,
  UseFormModalReturn,
} from './useFormModal';
export { useExtendedFormModal, useFormModal } from './useFormModal';
export type {
  UseModalFormOptions,
  UseModalFormReturn,
} from './useModalForm';
// Modal form hook (combines Form.useForm with dialog state)
export { useModalForm } from './useModalForm';
export type { UsePaginationOptions, UsePaginationReturn } from './usePagination';
export { useMultiPagination, usePagination } from './usePagination';
export type { UseTeamSelectionOptions, UseTeamSelectionReturn } from './useTeamSelection';
export { useTeamSelection } from './useTeamSelection';
export type { UnifiedModalState, UseUnifiedModalReturn } from './useUnifiedModal';
export { useUnifiedModal } from './useUnifiedModal';
