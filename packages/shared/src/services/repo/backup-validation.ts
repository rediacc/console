/**
 * Backup validation service
 * Handles validation for repo backup operations
 */

import { type RepoWithRelations, isFork } from './core';

/**
 * Result of backup validation
 */
export interface BackupValidationResult {
  canBackup: boolean;
  reason?: string;
}

/**
 * Check if a repo can backup to storage
 * Only grand repos (credentials) are allowed to backup to storage
 * Forks are blocked from storage backup
 * @param repo - Repo to check for backup eligibility
 * @returns Validation result with canBackup flag and reason if blocked
 */
export function canBackupToStorage(repo: RepoWithRelations): BackupValidationResult {
  // Only grand repos can backup to storage
  if (isFork(repo)) {
    return {
      canBackup: false,
      reason:
        'Forks cannot backup to storage. Only grand repos (credentials) can perform storage backups.',
    };
  }

  return {
    canBackup: true,
  };
}

/**
 * Check if a repo can backup to another machine
 * Both credentials and forks can backup to machines
 * @param _repo - Repo to check (unused, all repos can backup to machines)
 * @returns Validation result
 */
export function canBackupToMachine(_repo: RepoWithRelations): BackupValidationResult {
  // Any repo can backup to a machine
  return {
    canBackup: true,
  };
}

/**
 * Get backup options for a repo
 * @param repo - Repo to get backup options for
 * @returns Available backup options
 */
export function getBackupOptions(repo: RepoWithRelations): {
  canBackupToStorage: boolean;
  canBackupToMachine: boolean;
  storageReason?: string;
} {
  const storageResult = canBackupToStorage(repo);
  const machineResult = canBackupToMachine(repo);

  return {
    canBackupToStorage: storageResult.canBackup,
    canBackupToMachine: machineResult.canBackup,
    storageReason: storageResult.reason,
  };
}

/**
 * Validate backup destination
 * @param repo - Repo being backed up
 * @param destinationType - Type of destination ('storage' | 'machine')
 * @returns Validation result
 */
export function validateBackupDestination(
  repo: RepoWithRelations,
  destinationType: 'storage' | 'machine'
): BackupValidationResult {
  if (destinationType === 'storage') {
    return canBackupToStorage(repo);
  }

  return canBackupToMachine(repo);
}
