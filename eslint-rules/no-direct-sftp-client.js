/**
 * Forbid constructing an SFTPClient outside the connection pool.
 *
 * Every SSH/SFTP session must come from the refcounted pool in
 * services/machine/machine-connection.ts. A direct `new SFTPClient(...)` opens an
 * unpooled session (no reuse, no refcounting) and, in practice, every stray site
 * also forgot to pass `knownHosts`, so it silently skipped the host-key
 * verification that the pool's factory applies.
 *
 * Options: { allow: string[] } - path suffixes permitted to construct the client
 * (the pool itself). Defaults to the pool module.
 */

const DEFAULT_ALLOW = ['src/services/machine/machine-connection.ts'];

export const noDirectSftpClient = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Require SFTP sessions to come from the machine connection pool',
    },
    schema: [
      {
        type: 'object',
        properties: {
          allow: { type: 'array', items: { type: 'string' } },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      noDirectSftpClient:
        'Do not construct SFTPClient directly: it bypasses the connection pool and skips host-key verification. Take a lease instead - machineConnections.acquire(machineName) / acquireFor(machine, sshPrivateKey), or withPooledSftp(config) (services/machine/machine-connection.ts), and release it in a finally.',
    },
  },

  create(context) {
    const allow = context.options[0]?.allow ?? DEFAULT_ALLOW;
    const filename = context.filename.replaceAll('\\', '/');
    if (allow.some((suffix) => filename.endsWith(suffix))) {
      return {};
    }

    return {
      NewExpression(node) {
        if (node.callee.type === 'Identifier' && node.callee.name === 'SFTPClient') {
          context.report({ node, messageId: 'noDirectSftpClient' });
        }
      },
    };
  },
};
