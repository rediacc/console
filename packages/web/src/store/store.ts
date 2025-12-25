import { configureStore, Middleware } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';
import authSlice from './auth/authSlice';
import {
  machineAssignmentLoggingMiddleware,
  machineAssignmentMiddleware,
  machineSelectionPersistenceMiddleware,
} from './ceph/machineAssignmentMiddleware';
import machineAssignmentSlice from './ceph/machineAssignmentSlice';
import { telemetryMiddleware } from './middleware/telemetryMiddleware';
import notificationSlice from './notifications/notificationSlice';
import uiSlice from './ui/uiSlice';

// Define RootState type from reducer shape before store creation
const rootReducer = {
  auth: authSlice,
  ui: uiSlice,
  notifications: notificationSlice,
  machineAssignment: machineAssignmentSlice,
};

export type RootState = {
  auth: ReturnType<typeof authSlice>;
  ui: ReturnType<typeof uiSlice>;
  notifications: ReturnType<typeof notificationSlice>;
  machineAssignment: ReturnType<typeof machineAssignmentSlice>;
};

export const store = configureStore({
  reducer: rootReducer,
  middleware: (getDefaultMiddleware) => {
    const defaultMiddleware = getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['auth/setToken', 'machineAssignment/validateSelectedMachines/fulfilled'],
        ignoredPaths: [
          'machineAssignment.lastOperationResult.timestamp',
          'machineAssignment.operationHistory',
        ],
      },
    });

    const extraMiddleware = [
      telemetryMiddleware,
      machineAssignmentMiddleware,
      machineSelectionPersistenceMiddleware,
      import.meta.env.DEV ? machineAssignmentLoggingMiddleware : null,
    ].filter((mw): mw is Middleware => mw !== null);

    return defaultMiddleware.concat(...extraMiddleware);
  },
});

type AppDispatch = typeof store.dispatch;

// Export typed hooks
const useAppDispatch: () => AppDispatch = useDispatch;
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;

// Reserved for future use
void useAppDispatch;
