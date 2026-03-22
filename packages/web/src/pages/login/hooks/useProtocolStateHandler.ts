import type { FormInstance } from 'antd/es/form';
import type { LoginFormValues } from '@/features/auth/types';
import { showMessage } from '@/utils/messages';
import { getVaultProtocolMessage, VaultProtocolState } from '@/utils/vaultProtocol';

const FIELD_FOCUS_DELAY_MS = 100;

interface ProtocolHandlerResult {
  shouldReturn: boolean;
}

export const handleProtocolState = (
  protocolState: VaultProtocolState,
  t: (key: string) => string,
  form: FormInstance<LoginFormValues>,
  setError: (error: string) => void,
  setVaultProtocolState: (state: VaultProtocolState) => void
): ProtocolHandlerResult => {
  const protocolMessage = getVaultProtocolMessage(protocolState);
  const messageKey = protocolMessage.messageKey.replace('auth:', '');
  const translatedMessage = t(messageKey) || protocolMessage.message;

  switch (protocolState) {
    case VaultProtocolState.PASSWORD_REQUIRED:
      setError(translatedMessage);
      setVaultProtocolState(protocolState);
      setTimeout(() => {
        form.getFieldInstance('masterPassword')?.focus();
      }, FIELD_FOCUS_DELAY_MS);
      return { shouldReturn: true };

    case VaultProtocolState.INVALID_PASSWORD:
      setError(translatedMessage);
      setVaultProtocolState(protocolState);
      form.setFieldValue('masterPassword', '');
      setTimeout(() => {
        form.getFieldInstance('masterPassword')?.focus();
      }, FIELD_FOCUS_DELAY_MS);
      return { shouldReturn: true };

    case VaultProtocolState.PASSWORD_NOT_NEEDED:
      if (translatedMessage && translatedMessage !== messageKey) {
        showMessage('warning', translatedMessage);
      } else {
        showMessage('warning', protocolMessage.message);
      }
      return { shouldReturn: false };

    case VaultProtocolState.VALID:
      return { shouldReturn: false };

    default:
      return { shouldReturn: false };
  }
};
