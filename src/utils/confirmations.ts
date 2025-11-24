import type { HookAPI as ModalHookAPI } from 'antd/es/modal/useModal'
import type { TFunction } from 'i18next'
import { showMessage } from './messages'

export interface ConfirmDeleteConfig {
  modal: ModalHookAPI
  t: TFunction
  resourceType: string
  resourceName: string
  translationNamespace?: string
  onConfirm: () => Promise<unknown>
  onSuccess?: () => void
  onError?: (error: Error) => void
}

/**
 * Show a standardized delete confirmation dialog
 *
 * @example
 * confirmDelete({
 *   modal,
 *   t,
 *   resourceType: 'machine',
 *   resourceName: machine.machineName,
 *   translationNamespace: 'machines',
 *   onConfirm: () => deleteMutation.mutateAsync({ machineName }),
 *   onSuccess: () => refetch()
 * })
 */
export function confirmDelete({
  modal,
  t,
  resourceType,
  resourceName,
  translationNamespace,
  onConfirm,
  onSuccess,
  onError
}: ConfirmDeleteConfig): void {
  const ns = translationNamespace || resourceType + 's'

  modal.confirm({
    title: t(`${ns}:confirmDelete`) as string,
    content: t(`${ns}:deleteWarning`, { name: resourceName, [resourceType + 'Name']: resourceName }) as string,
    okText: t('common:actions.delete'),
    okType: 'danger',
    cancelText: t('common:actions.cancel'),
    onOk: async () => {
      try {
        await onConfirm()
        showMessage('success', t(`${ns}:deleteSuccess`))
        onSuccess?.()
      } catch (error) {
        showMessage('error', t(`${ns}:deleteError`))
        onError?.(error as Error)
      }
    }
  })
}

export interface ConfirmActionConfig {
  modal: ModalHookAPI
  title: string
  content: string
  okText: string
  okType?: 'primary' | 'danger'
  cancelText: string
  onConfirm: () => Promise<void>
  onSuccess?: () => void
  successMessage?: string
  errorMessage?: string
  onError?: (error: Error) => void
}

/**
 * Show a generic confirmation dialog for any action
 *
 * @example
 * confirmAction({
 *   modal,
 *   title: 'Reassign Machine',
 *   content: 'Are you sure you want to reassign this machine?',
 *   okText: 'Reassign',
 *   cancelText: 'Cancel',
 *   onConfirm: () => reassignMutation.mutateAsync(data),
 *   successMessage: 'Machine reassigned successfully'
 * })
 */
export function confirmAction({
  modal,
  title,
  content,
  okText,
  okType = 'primary',
  cancelText,
  onConfirm,
  onSuccess,
  successMessage,
  errorMessage,
  onError
}: ConfirmActionConfig): void {
  modal.confirm({
    title,
    content,
    okText,
    okType,
    cancelText,
    onOk: async () => {
      try {
        await onConfirm()
        if (successMessage) {
          showMessage('success', successMessage)
        }
        onSuccess?.()
      } catch (error) {
        if (errorMessage) {
          showMessage('error', errorMessage)
        }
        onError?.(error as Error)
      }
    }
  })
}
