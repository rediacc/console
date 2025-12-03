import { useCallback } from 'react'
import { Form } from 'antd'
import type { FormInstance } from 'antd/es/form'
import { useDialogState } from './useDialogState'
import type { UseDialogStateReturn } from './useDialogState'

/**
 * Options for useModalForm hook
 */
export interface UseModalFormOptions<T extends Record<string, unknown>> {
  /** Initial form values */
  initialValues?: FormValues<T>
  /** Whether to reset form on modal close (default: true) */
  resetOnClose?: boolean
}

/**
 * Return type for useModalForm hook
 */
export interface UseModalFormReturn<T extends Record<string, unknown> = Record<string, unknown>> {
  /** Ant Design form instance */
  form: FormInstance<T>
  /** Whether the modal is open */
  isOpen: boolean
  /** Open the modal */
  open: () => void
  /** Close the modal and optionally reset form */
  close: () => void
  /** Close modal with form reset */
  closeAndReset: () => void
  /** Reset the form to initial values */
  reset: () => void
  /** The underlying dialog state return for advanced usage */
  dialogState: UseDialogStateReturn<void>
}

/**
 * Hook that combines Form.useForm with modal state management.
 * Automatically resets the form when the modal is closed.
 *
 * @example
 * const { form, isOpen, open, close } = useModalForm<{ password: string }>()
 *
 * return (
 *   <>
 *     <Button onClick={open}>Open Form</Button>
 *     <Modal open={isOpen} onCancel={close}>
 *       <Form form={form} onFinish={handleSubmit}>
 *         <Form.Item name="password">
 *           <Input.Password />
 *         </Form.Item>
 *       </Form>
 *     </Modal>
 *   </>
 * )
 *
 * @example
 * // With initial values
 * const { form, isOpen, open, close } = useModalForm({
 *   initialValues: { email: '', password: '' }
 * })
 *
 * @example
 * // Disable auto-reset on close
 * const { form, isOpen, open, closeAndReset } = useModalForm({
 *   resetOnClose: false
 * })
 * // Then explicitly call closeAndReset when needed
 */
export function useModalForm<T extends Record<string, unknown> = Record<string, unknown>>(
  options: UseModalFormOptions<T> = {}
): UseModalFormReturn<T> {
  const { initialValues, resetOnClose = true } = options
  const [form] = Form.useForm<T>()
  const dialogState = useDialogState<void>()

  const reset = useCallback(() => {
    if (initialValues) {
      form.setFieldsValue(initialValues)
    } else {
      form.resetFields()
    }
  }, [form, initialValues])

  const closeAndReset = useCallback(() => {
    dialogState.close()
    reset()
  }, [dialogState, reset])

  const close = useCallback(() => {
    if (resetOnClose) {
      closeAndReset()
    } else {
      dialogState.close()
    }
  }, [closeAndReset, dialogState, resetOnClose])

  return {
    form,
    isOpen: dialogState.isOpen,
    open: dialogState.open,
    close,
    closeAndReset,
    reset,
    dialogState,
  }
}
type FormValues<T extends Record<string, unknown>> = Parameters<FormInstance<T>['setFieldsValue']>[0]
