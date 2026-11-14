export type RollbackState = 'rolled-back' | 'running' | 'failed';

/** What the migrate error tells the operator about the rollback: a rollback phase still running has not failed, so no manual command is advised beside it. */
export function describeRollback(state: RollbackState, controlName: string): string {
  if (state === 'running') {
    return `failed at the destination attach, and the rollback to "${controlName}" is STILL RUNNING; wait for it with "rdc job wait" and check "${controlName}" before running anything by hand. `;
  }
  if (state === 'failed') {
    return `failed at the destination attach, and the rollback to "${controlName}" did NOT finish. `;
  }
  return `failed at the destination attach and was ROLLED BACK to "${controlName}" (control datastore re-attached + control plane restarted). `;
}

export interface MigrateAttachFailure {
  clusterName: string;
  rollback: RollbackState;
  controlName: string;
  controlDs: string;
  controlDsMount: string;
  controlIp: string;
  original: string;
}

/**
 * The error for a migrate that failed at the destination attach. The manual
 * recovery commands are named only when the rollback is not still running, since
 * running them beside a live rollback is the race the 'running' text warns about.
 */
export function describeMigrateAttachFailure(f: MigrateAttachFailure): string {
  const manual =
    f.rollback === 'running'
      ? ''
      : `If the source did not recover, on ${f.controlName} run: renet datastore attach --name ${f.controlDs} --force, then ` +
        `renet kube identity-rewrite --mount-path ${f.controlDsMount} --operation migrate --new-node-ip ` +
        `${f.controlIp}. `;
  return (
    `cluster migrate "${f.clusterName}" ${describeRollback(f.rollback, f.controlName)}` +
    `The dest's adopted record is harmless (registry-only) and is reused on retry. ${manual}` +
    `Original error: ${f.original}`
  );
}
