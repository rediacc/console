import { DEFAULTS } from '@rediacc/shared/config';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { PreconditionValidationError } from '../../utils/errors.js';
import { getEffectiveConfigName } from '../config/config-name.js';

/**
 * Refuse to write account state or a token for a named config that does not exist. Named configs
 * are made only by `rdc config init <name>`; the default config is auto-created, so it never
 * refuses. Without this, `--config typo subscription login` prompted for a region that
 * patchActiveAccount then dropped, authorized against the default region, and left a token beside
 * a config that is not there. Call it before any prompt, network call or write.
 */
export async function assertActiveConfigExists(): Promise<void> {
  const name = getEffectiveConfigName();
  if (name === DEFAULTS.CONTEXT.CONFIG_NAME) return;
  if (await configFileStorage.exists(name)) return;
  throw new PreconditionValidationError(
    t('errors.config.missingNamed', { name }),
    {
      summary: t('errors.config.missingNamed', { name }),
      options: [{ description: `Create the config "${name}"`, run: `rdc config init ${name}` }],
    },
    ERROR_CODES.NOT_FOUND
  );
}
