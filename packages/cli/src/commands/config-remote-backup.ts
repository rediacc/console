import { promises as fs } from 'node:fs';

/**
 * The UTC stamp of the pre-enable copy's name: `YYYYMMDDTHHMMSSZ`, sortable and free of the `:` that Windows
 * refuses in a file name.
 */
function utcStamp(now: Date): string {
  return now
    .toISOString()
    .replace(/\.\d{3}Z$/, 'Z')
    .replace(/[-:]/g, '');
}

/** The name the pre-enable copy is written under before any same-second counter. */
export function preEnableBackupName(configPath: string, now: Date): string {
  return `${configPath}.pre-enable.${utcStamp(now)}.bak`;
}

/** The copies of one second collide only when enable runs twice inside it; the counter keeps both. */
const MAX_SAME_SECOND_COPIES = 100;

/** The nth candidate name of one second: the plain name, then `-1`, `-2`, and so on. */
function candidateName(configPath: string, now: Date, attempt: number): string {
  const base = preEnableBackupName(configPath, now).slice(0, -'.bak'.length);
  return `${base}${attempt === 0 ? '' : `-${attempt}`}.bak`;
}

/**
 * The name the next copy will be written under, counter included, for a prompt that names it ahead of
 * the write: the first candidate no file holds yet.
 */
export async function nextPreEnableBackupName(configPath: string, now: Date): Promise<string> {
  for (let attempt = 0; attempt < MAX_SAME_SECOND_COPIES; attempt++) {
    const target = candidateName(configPath, now, attempt);
    try {
      await fs.access(target);
    } catch {
      return target;
    }
  }
  throw new Error(`Too many pre-enable copies of ${configPath} in one second`);
}

/**
 * Copy the config file as it stands before `config remote enable` rewrites it, to
 * `<file>.pre-enable.<UTC stamp>.bak`, and return the copy's path (null when the file does not exist yet,
 * so there is nothing to keep). The copy is never overwritten: the generic `.bak` that every save writes is
 * last-save-wins by design, so a second enable replaced the first one's only record of the pre-enable
 * content (2026-11-25), and a name per enable keeps each of them.
 */
export async function writePreEnableBackup(
  configPath: string,
  now: Date = new Date()
): Promise<string | null> {
  for (let attempt = 0; attempt < MAX_SAME_SECOND_COPIES; attempt++) {
    const target = candidateName(configPath, now, attempt);
    const outcome = await copyOnce(configPath, target);
    if (outcome !== 'exists') return outcome;
  }
  throw new Error(`Too many pre-enable copies of ${configPath} in one second`);
}

/** One exclusive copy: the target's path, null when the source is absent, or 'exists' when the target name is taken. */
async function copyOnce(source: string, target: string): Promise<string | null | 'exists'> {
  try {
    await fs.copyFile(source, target, fs.constants.COPYFILE_EXCL);
    await fs.chmod(target, 0o600);
    return target;
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT') return null;
    if (code === 'EEXIST') return 'exists';
    throw error;
  }
}
