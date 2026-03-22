export { UPDATE_STATE_DEFAULTS } from './constants';
export { isCooldownExpired } from './cooldown';
export { readUpdateState, writeUpdateState } from './state-io';
export type {
  CliUpdateState,
  DesktopUpdateState,
  PendingUpdate,
  UpdateStateBase,
} from './types';
