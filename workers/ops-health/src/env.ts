import type { OpsState } from './state';

/**
 * The bindings, vars and secrets of the ops-health Worker. Every secret is optional at the type level, because a missing one is a setup failure the Worker reports as an `unknown` probe (`targets`, `mailer`) or a 401, never a crash.
 */
export interface Env {
  OPS_STATE: DurableObjectNamespace<OpsState>;
  /** The target file read out of the `ops` repo at deploy time (rediacc_ci.ops.deploy_ops_health). */
  OPS_HEALTH_TARGETS?: string;
  /** sha256 of OPS_HEALTH_TARGETS, a var set by the deploy, reported by /v1/status. */
  OPS_HEALTH_TARGETS_SHA?: string;
  /** sha256 of the deployed source tree, a var set by the deploy so a re-run can tell nothing changed. */
  OPS_HEALTH_CODE_SHA?: string;
  /** Salted digests of the deployed secrets (`NAME=hex,NAME=hex`), a var set by the deploy for the same reason. */
  OPS_HEALTH_SECRET_DIGESTS?: string;
  OPS_HEALTH_READ_TOKEN?: string;
  OPS_HEALTH_INGEST_TOKEN?: string;
  /** Comma-separated recipients; an empty list is the `mailer` probe in state `unknown`. */
  OPS_ALERT_EMAILS?: string;
  AWS_SES_ACCESS_KEY_ID_EU?: string;
  AWS_SES_SECRET_ACCESS_KEY_EU?: string;
  AWS_SES_REGION_EU?: string;
  /** The sender, the plain var OPS_MAIL_FROM in wrangler.toml, not a secret. */
  OPS_MAIL_FROM?: string;
  /** Optional Spamhaus Data Query Service key; without it a Spamhaus zone is `unknown`. */
  SPAMHAUS_DQS_KEY?: string;
}
