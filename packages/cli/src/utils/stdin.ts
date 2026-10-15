/**
 * Read all of stdin as UTF-8, minus one trailing newline (the one `echo`,
 * `printf '%s\n'` or `cat` adds); internal newlines are kept. The read path
 * for a value passed as `-`, which keeps a secret off argv and out of the
 * process list.
 */
export async function readStdinValue(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : (chunk as Buffer));
  }
  return Buffer.concat(chunks).toString('utf-8').replace(/\n$/, '');
}
