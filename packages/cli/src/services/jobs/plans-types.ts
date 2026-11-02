/** Types and shared note strings of the job plan tables (plans.ts). */

/** renet's lock classes (overlap.go LockClass). */
export const LOCK_CLASSES = [
  'repo-exclusive',
  'repo-shared',
  'machine-exclusive',
  'machine-shared',
  'control',
  'read',
] as const;
type LockClass = (typeof LOCK_CLASSES)[number];

/** Section 20's two timeout classes. */
export const TIMEOUT_CLASSES = ['10m', '24h'] as const;
type TimeoutClass = (typeof TIMEOUT_CLASSES)[number];

/**
 * The single-job form (J0b column 3).
 *
 * - `single`: one renet call.
 * - `precondition`: the probes fold into the job as preconditions.
 * - `command-kind`: a raw renet subcommand on the section 14 allow-list.
 * - `compound`: several calls, as one compound function or a chain under one ticket.
 * - `successor`: one job, then a successor job recorded on the ticket.
 */
type JobForm = 'single' | 'precondition' | 'command-kind' | 'compound' | 'successor';

type ConversionBox = 'J4' | 'J16' | 'J17' | 'J18' | 'J19' | 'J20';

export interface JobPlan {
  form: JobForm;
  /** The renet function or command kind the job runs, as overlap.go names it. */
  fn?: string;
  lock: LockClass;
  /** The class when the job names no repository (`-m`, the survey forms). */
  lockWithoutRepo?: LockClass;
  timeout: TimeoutClass;
  box: ConversionBox;
  /** Client-side steps after the job, by registered step name (steps.ts). */
  steps?: readonly string[];
  /** A section 24 exception for one form of the command (an interactive or a local leg). */
  exception?: string;
  /** Why the plan names no `fn`, or what else the conversion box must know. */
  note?: string;
  /** For a plan with no `fn`: the overlap.go name (a command kind) its `lock` is read from. */
  lockFrom?: string;
  /**
   * For a plan with no `fn`: the renet function or kind it runs that overlap.go either does not
   * list (its fallback rules classify it) or classifies differently from `lock`. `overlap` is what
   * overlap.go gives it today, so a change in overlap.go fails the coverage test. A listed name
   * whose class agrees with `lock` is a `lockFrom`, not a gap.
   */
  lockGap?: { runs: string; overlap: LockClass };
}

export const NEW_KIND =
  'runs as a command kind that is not on the section 14 allow-list yet (J0b finding 4)';
export const CHAIN =
  'a chain across calls or machines with no compound renet function yet (J0b finding 9)';
