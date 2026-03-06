import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Alert } from 'antd';
import React from 'react';

interface Team {
  teamName: string;
  vaultContent?: string | null;
}

interface SSHKeyWarningProps {
  teamName: string;
  teams?: Team[];
  t: TypedTFunction;
}

export const SSHKeyWarning: React.FC<SSHKeyWarningProps> = ({ teamName, teams, t }) => {
  const team = teams?.find((t) => t.teamName === teamName);
  if (!team?.vaultContent) return null;

  let missingSSHKeys = false;
  try {
    const teamVault = JSON.parse(team.vaultContent);
    missingSSHKeys = !teamVault.SSH_PRIVATE_KEY || !teamVault.SSH_PUBLIC_KEY;
  } catch {
    return null;
  }

  if (!missingSSHKeys) return null;

  return (
    <Alert
      type="warning"
      closable
      message={t('common:vaultEditor.missingSshKeysWarning')}
      description={t('common:vaultEditor.missingSshKeysDescription')}
    />
  );
};
