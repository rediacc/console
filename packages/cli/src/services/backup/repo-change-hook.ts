/**
 * The G4 hook every repository-set change calls: create, delete, fork and the promote rename.
 *
 * The schedule module is imported lazily so a repo verb that never changes the set does not load the
 * unit generator, and so the verbs' own tests need not mock it.
 * reconcileSchedulesAfterRepoChange warns and never throws: the repository change already happened.
 */
export async function reconcileBackupSchedules(machine: string): Promise<void> {
  const { reconcileSchedulesAfterRepoChange } = await import('./backup-schedule.js');
  await reconcileSchedulesAfterRepoChange(machine);
}
