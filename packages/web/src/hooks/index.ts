// Custom hooks for reducing code duplication

export type {
  SFTPConnectionOptions,
  SFTPFile,
  UseSftpActions,
  UseSftpState,
} from './sftp/useSftp';
// SFTP hook for file browser operations in Electron
export { useSftp } from './sftp/useSftp';
export type { TerminalStatus, UseTerminalOptions, UseTerminalReturn } from './terminal';
// Terminal hook for SSH sessions in Electron
export { useTerminal } from './terminal';
export type { AsyncActionConfig, AsyncActionResult, UseAsyncActionReturn } from './useAsyncAction';
// Async action handling
export { useAsyncAction } from './useAsyncAction';
export type { UseCopyToClipboardOptions, UseCopyToClipboardReturn } from './useCopyToClipboard';
// Clipboard copy hook with visual feedback
export { useCopyToClipboard } from './useCopyToClipboard';
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
export type { MessageOptions, UseMessageReturn } from './useMessage';
// Toast notification hook with i18n support
export { useMessage } from './useMessage';
export type {
  UseModalFormOptions,
  UseModalFormReturn,
} from './useModalForm';
// Modal form hook (combines Form.useForm with dialog state)
export { useModalForm } from './useModalForm';
export type { UsePaginationOptions, UsePaginationReturn } from './usePagination';
export { useMultiPagination, usePagination } from './usePagination';
export type { UnifiedModalState, UseUnifiedModalReturn } from './useUnifiedModal';
export { useUnifiedModal } from './useUnifiedModal';
