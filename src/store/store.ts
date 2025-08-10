import { configureStore } from '@reduxjs/toolkit'
import { useDispatch, useSelector, TypedUseSelectorHook } from 'react-redux'
import authSlice from './auth/authSlice'
import uiSlice from './ui/uiSlice'
import notificationSlice from './notifications/notificationSlice'
import machineAssignmentSlice from './distributedStorage/machineAssignmentSlice'
import { 
  machineAssignmentMiddleware,
  machineSelectionPersistenceMiddleware,
  machineAssignmentLoggingMiddleware
} from './distributedStorage/machineAssignmentMiddleware'

export const store = configureStore({
  reducer: {
    auth: authSlice,
    ui: uiSlice,
    notifications: notificationSlice,
    machineAssignment: machineAssignmentSlice,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['auth/setToken', 'machineAssignment/validateSelectedMachines/fulfilled'],
        ignoredPaths: [
          'machineAssignment.lastOperationResult.timestamp',
          'machineAssignment.operationHistory'
        ],
      },
    }).concat(
      machineAssignmentMiddleware,
      machineSelectionPersistenceMiddleware,
      import.meta.env.DEV ? machineAssignmentLoggingMiddleware : []
    ).filter(Boolean),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch

// Export typed hooks
export const useAppDispatch: () => AppDispatch = useDispatch
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector