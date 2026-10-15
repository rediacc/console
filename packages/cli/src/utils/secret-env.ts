/**
 * Per-repo env-mode secrets reach a remote shell as `REDIACC_SECRET_<NAME>`.
 * Their values never ride a command line (local argv, the remote `ps`); a
 * session receives them through the SSH environment instead: the local ssh
 * process holds them in its environment and `SendEnv` names them, and the
 * machine's sshd accepts `REDIACC_*` (renet setup writes the AcceptEnv drop-in).
 */

const SECRET_ENV_PREFIX = 'REDIACC_SECRET_';

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

function isSecretEnvName(name: string): boolean {
  return name.startsWith(SECRET_ENV_PREFIX);
}

/** Split an environment into the values a command line may carry and the secret names. */
export function splitSecretEnv(env: Record<string, string> | undefined): {
  plain: Record<string, string>;
  secretNames: string[];
} {
  const plain: Record<string, string> = {};
  const secretNames: string[] = [];
  for (const [key, value] of Object.entries(env ?? {})) {
    if (isSecretEnvName(key)) secretNames.push(key);
    else plain[key] = value;
  }
  return { plain, secretNames };
}

/**
 * The ssh options that forward the named variables from the ssh process's
 * environment. One `-o SendEnv=NAME` per name: no glob and no space, so the
 * options survive being joined into a shell command string unquoted.
 */
export function sendEnvOptions(names: string[]): string[] {
  return names.flatMap((name) => {
    if (!ENV_NAME.test(name)) throw new Error(`Invalid environment variable name: ${name}`);
    return ['-o', `SendEnv=${name}`];
  });
}
