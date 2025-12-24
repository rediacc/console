import React from 'react';
import { Alert } from 'antd';
import type { TFunction } from 'i18next';

interface Team {
  teamName: string;
  vaultContent?: string | null;
}

interface SSHKeyWarningProps {
  teamName: string;
  teams?: Team[];
  t: TFunction;
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
      showIcon
      closable
      message={t('common:vaultEditor.missingSshKeysWarning')}
      description={t('common:vaultEditor.missingSshKeysDescription')}
    />
  );
};
