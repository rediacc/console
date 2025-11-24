/**
 * Backup validation service
 * Handles validation for repository backup operations
 */

import { type RepositoryWithRelations, isFork } from '../repository'

/**
 * Result of backup validation
 */
export interface BackupValidationResult {
  canBackup: boolean
  reason?: string
}

/**
 * Check if a repository can backup to storage
 * Only grand repositories (credentials) are allowed to backup to storage
 * Forks are blocked from storage backup
 * @param repository - Repository to check for backup eligibility
 * @returns Validation result with canBackup flag and reason if blocked
 */
export function canBackupToStorage(
  repository: RepositoryWithRelations
): BackupValidationResult {
  // Only grand repositories can backup to storage
  if (isFork(repository)) {
    return {
      canBackup: false,
      reason: 'Forks cannot backup to storage. Only grand repositories (credentials) can perform storage backups.'
    }
  }

  return {
    canBackup: true
  }
}

/**
 * Check if a repository can backup to another machine
 * Both credentials and forks can backup to machines
 * @param _repository - Repository to check (unused, all repos can backup to machines)
 * @returns Validation result
 */
export function canBackupToMachine(
  _repository: RepositoryWithRelations
): BackupValidationResult {
  // Any repository can backup to a machine
  return {
    canBackup: true
  }
}

/**
 * Get backup options for a repository
 * @param repository - Repository to get backup options for
 * @returns Available backup options
 */
export function getBackupOptions(
  repository: RepositoryWithRelations
): {
  canBackupToStorage: boolean
  canBackupToMachine: boolean
  storageReason?: string
} {
  const storageResult = canBackupToStorage(repository)
  const machineResult = canBackupToMachine(repository)

  return {
    canBackupToStorage: storageResult.canBackup,
    canBackupToMachine: machineResult.canBackup,
    storageReason: storageResult.reason
  }
}

/**
 * Validate backup destination
 * @param repository - Repository being backed up
 * @param destinationType - Type of destination ('storage' | 'machine')
 * @returns Validation result
 */
export function validateBackupDestination(
  repository: RepositoryWithRelations,
  destinationType: 'storage' | 'machine'
): BackupValidationResult {
  if (destinationType === 'storage') {
    return canBackupToStorage(repository)
  }

  return canBackupToMachine(repository)
}
