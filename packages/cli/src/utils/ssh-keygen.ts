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
  // ssh2's ed25519 OpenSSH encoder mis-pads the private section on ~0.6% of
  // generations (private blob 3 bytes short) -- OpenSSH then rejects the key
  // with "error in libcrypto" at CONNECT time, long after generation, as an
  // intermittent auth failure (reproduced locally: 3/500 bad; caught live by
  // the CI tutorial sequence on repo-ref connects). ssh2's own parseKey
  // rejects exactly the malformed outputs, so validate and retry: at 0.6%
  // per draw, five draws make a bad pair astronomically unlikely.
  for (let attempt = 0; attempt < 5; attempt++) {
    const keys = ssh2.utils.generateKeyPairSync('ed25519', { comment });
    if (!(ssh2.utils.parseKey(keys.private) instanceof Error)) {
      return {
        privateKey: keys.private,
        publicKey: keys.public,
      };
    }
  }
  throw new Error('ssh2 produced a malformed ed25519 key on 5 consecutive attempts');
}
