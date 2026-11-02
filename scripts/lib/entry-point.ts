/**
 * "Was this module run, or was it loaded?", answered once.
 *
 * A gate that exports its helpers must not run `main()` when imported, and must run it when
 * launched. Callers pass `import.meta.filename`. Both sides go through `fs.realpathSync`
 * because Node and tsx set `import.meta.filename` to the symlink-resolved real path while
 * `process.argv[1]` keeps the symlink the script was launched through, so a plain
 * `path.resolve(argv1) === filename` is false through a symlinked directory and main() never
 * runs: the gate exits 0 having checked nothing. A path with a space also breaks any
 * comparison built on a `file://` string (the URL is percent-encoded). An unresolvable
 * path on either side is not the entry point.
 */
import fs from 'node:fs';
import process from 'node:process';

export function isEntryPoint(filename: string): boolean {
  // A module URL (`import.meta.url`) is never a path, so it throws: returning false would silently skip a gate's main() and the gate would exit 0 having checked nothing.
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(filename)) {
    throw new Error(
      `isEntryPoint takes a file path (import.meta.filename), got a URL: ${filename}`
    );
  }
  const invoked = process.argv[1];
  if (!invoked) return false;
  try {
    return fs.realpathSync(invoked) === fs.realpathSync(filename);
  } catch {
    return false;
  }
}

/** When this module is the entry point, exit with `main`'s status for the arguments after the script path. */
export function exitWithMainIfEntryPoint(filename: string, main: (argv: string[]) => number): void {
  if (isEntryPoint(filename)) process.exit(main(process.argv.slice(2)));
}
