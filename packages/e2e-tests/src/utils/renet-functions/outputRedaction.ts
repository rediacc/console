/**
 * Output redaction for commands whose stdout IS a secret (a k3s join token, a kubeconfig with client keys).
 * The caller still receives the real value; only the log line changes, to a byte count.
 *
 * A per-call flag was chosen over a value scrubber because the secret here is minted by the product on the VM, so the runner never
 * holds it before the output arrives. The flag lives on the wrapper method (KubeMethods.kubeJoinToken / kubeKubeconfig), not on each
 * call site, so no test can forget it.
 */
export function formatExecutionLog(
  stdout: string,
  stderr: string,
  code: number,
  redact = false
): string[] {
  const lines: string[] = [];
  if (stdout.trim()) {
    lines.push(
      redact ? `[STDOUT] ${Buffer.byteLength(stdout)} bytes (redacted)` : `[STDOUT]\n${stdout}`
    );
  }
  if (stderr.trim()) {
    lines.push(
      redact ? `[STDERR] ${Buffer.byteLength(stderr)} bytes (redacted)` : `[STDERR]\n${stderr}`
    );
  }
  lines.push(`[EXIT] ${code}`);
  return lines;
}
