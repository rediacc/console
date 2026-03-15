/**
 * VS Code Command Utilities
 * Display helper functions for VS Code Remote SSH CLI commands
 */

import { t } from '../i18n/index.js';
import { outputService } from '../services/output.js';

export interface VSCodeInstallationInfo {
  path: string;
  version?: string;
  isInsiders?: boolean;
}

/**
 * Display VS Code installation information
 */
export function displayVSCodeInstallation(vscode: VSCodeInstallationInfo | null): void {
  outputService.info(t('commands.vscode.check.installation'));

  if (!vscode) {
    outputService.info(t('commands.vscode.check.vscodeNotFound'));
    return;
  }

  outputService.info(t('commands.vscode.check.vscodeFound', { path: vscode.path }));
  if (vscode.version) {
    outputService.info(t('commands.vscode.check.version', { version: vscode.version }));
  }
  if (vscode.isInsiders) {
    outputService.info(t('commands.vscode.check.variant'));
  }
}

/**
 * Display VS Code configuration status
 */
export function displayConfigurationStatus(configCheck: {
  configured: boolean;
  settingsPath: string;
  missing: string[];
}): void {
  outputService.info(t('commands.vscode.check.settingsPath', { path: configCheck.settingsPath }));
  outputService.info(
    t('commands.vscode.check.configured', {
      status: configCheck.configured
        ? t('commands.vscode.check.yes')
        : t('commands.vscode.check.no'),
    })
  );
  if (configCheck.missing.length > 0) {
    outputService.info(t('commands.vscode.check.missingSettings'));
    configCheck.missing.forEach((setting) => {
      outputService.info(`    - ${setting}`);
    });
  }
}

/**
 * Display active SSH connections
 */
export function displayActiveConnections(connections: string[]): void {
  outputService.info(t('commands.vscode.check.activeConnections', { count: connections.length }));

  connections.forEach((conn) => {
    outputService.info(`  - ${conn}`);
  });
}
