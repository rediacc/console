/**
 * Installs the pinned, sha256-verified OpenTofu into rdc's tools directory (the directory the
 * provider-lock test looks in) and prints its path. CI runs it before the CLI unit tests, where the
 * `tofu init` refusal tests must run rather than skip.
 */
import { installTofu } from '../src/services/tools/install.js';

const result = await installTofu();
process.stdout.write(`${result.path}\n`);
