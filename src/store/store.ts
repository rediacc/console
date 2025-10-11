import { configureStore, Middleware } from '@reduxjs/toolkit'
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
import { telemetryMiddleware } from './middleware/telemetryMiddleware'

// Define RootState type from reducer shape before store creation
const rootReducer = {
  auth: authSlice,
  ui: uiSlice,
  notifications: notificationSlice,
  machineAssignment: machineAssignmentSlice,
}

export type RootState = {
  auth: ReturnType<typeof authSlice>
  ui: ReturnType<typeof uiSlice>
  notifications: ReturnType<typeof notificationSlice>
  machineAssignment: ReturnType<typeof machineAssignmentSlice>
}

export const store = configureStore({
  reducer: rootReducer,
  middleware: (getDefaultMiddleware) => {
    const middleware = getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['auth/setToken', 'machineAssignment/validateSelectedMachines/fulfilled'],
        ignoredPaths: [
          'machineAssignment.lastOperationResult.timestamp',
          'machineAssignment.operationHistory'
        ],
      },
    }).concat(
      telemetryMiddleware as Middleware,
      machineAssignmentMiddleware as Middleware,
      machineSelectionPersistenceMiddleware as Middleware,
      import.meta.env.DEV ? (machineAssignmentLoggingMiddleware as Middleware) : ([] as unknown as Middleware)
    ).filter(Boolean) as any

    return middleware
  },
})

export type AppDispatch = typeof store.dispatch

// Export typed hooks
export const useAppDispatch: () => AppDispatch = useDispatch
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector