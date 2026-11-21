/**
 * The `background` flag of the proxy command request (finding #d31b4054): `-b` through
 * `--proxy` must reach the executor, so the schema carries it and does not strip it.
 */
import { describe, expect, it } from 'vitest';
import { CommandRequestSchema } from '../wire.js';

const base = { contractVersion: 'v1', pathKey: 'repo up', positionals: { ref: 'shop' } };

describe('CommandRequestSchema background', () => {
  it('round-trips background: true through parse and JSON', () => {
    const parsed = CommandRequestSchema.parse({ ...base, background: true });
    expect(parsed.background).toBe(true);
    expect(CommandRequestSchema.parse(JSON.parse(JSON.stringify(parsed))).background).toBe(true);
  });

  it('leaves background absent when the client did not send it', () => {
    expect(CommandRequestSchema.parse(base).background).toBeUndefined();
  });

  it('rejects a non-boolean background', () => {
    expect(CommandRequestSchema.safeParse({ ...base, background: 'yes' }).success).toBe(false);
  });
});
