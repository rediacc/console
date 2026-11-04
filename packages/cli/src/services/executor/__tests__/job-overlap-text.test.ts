import { describe, expect, it } from "vitest";
import { JobOverlapRefusedError } from "../detached-execution.js";
import { overlapWarningLines } from "../job-client.js";

describe("overlap warning text comes from the en catalog", () => {
  it("renders a refusal with its subject, origin and attach line", () => {
    const lines = overlapWarningLines({
      action: "refuse",
      jobId: "j1-abcdef01",
      function: "repository_up",
      repo: "mail",
      state: "running",
      startedAt: "2026-11-04T10:00:00Z",
      origin: { sshUser: "ops", client: "rdc", config: { name: "eu" } },
      attach: "rdc job wait j1-abcdef01",
    } as never);
    expect(lines).toEqual([
      "Refused: job j1-abcdef01 (repository_up on mail) is running, started 2026-11-04T10:00:00Z, started by ops via rdc (config eu).",
      "  See it: rdc job wait j1-abcdef01",
    ]);
  });

  it("falls back to the older-renet origin text", () => {
    const [head] = overlapWarningLines({
      action: "warn",
      jobId: "j2-00000000",
    } as never);
    expect(head).toBe(
      "Warning: job j2-00000000 (work) is running, started by: unknown (older renet).",
    );
  });

  it("drives the BUSY refusal: holder, machine and stop-it id fill their placeholders", () => {
    const error = new JobOverlapRefusedError(
      [
        {
          action: "refuse",
          jobId: "j1-abcdef01",
          function: "repository_up",
          repo: "mail",
        } as never,
      ],
      "m1",
    );
    expect(error.message).toBe(
      "Refused to start the job on 'm1': job j1-abcdef01 holds the same scope.",
    );
    expect(error.details).toContain(
      "  Or stop it: rdc job cancel j1-abcdef01 -m m1",
    );
    expect(`${error.message}${error.details?.join("")}`).not.toContain("{{");
  });

  it("control: a refusal without a job id names another job and offers no stop-it line", () => {
    const error = new JobOverlapRefusedError(
      [{ action: "refuse", unit: "u1" } as never],
      "m1",
    );
    expect(error.message).toContain("job u1");
    const none = new JobOverlapRefusedError([], "m1");
    expect(none.message).toBe(
      "Refused to start the job on 'm1': another job holds the same scope.",
    );
    expect(none.details?.some((d) => d.includes("Or stop it"))).toBe(false);
  });
});
