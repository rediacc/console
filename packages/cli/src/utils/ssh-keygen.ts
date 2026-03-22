import ssh2 from 'ssh2';

/**
 * Generates an ed25519 SSH key pair in OpenSSH format.
 * Used for per-repo SSH keys that enable server-side sandbox isolation.
 *
 * Uses the ssh2 library (already a project dependency) for pure-JS key generation.
 * No external executables needed.
 */
export function generateSSHKeyPair(comment = 'rediacc-repo-key'): {
  privateKey: string;
  publicKey: string;
} {
  const keys = ssh2.utils.generateKeyPairSync('ed25519', { comment });
  return {
    privateKey: keys.private,
    publicKey: keys.public,
  };
}
