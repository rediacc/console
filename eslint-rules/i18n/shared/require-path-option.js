import fs from 'node:fs';
import path from 'node:path';

/**
 * Resolve a mandatory directory option for an i18n rule.
 *
 * These rules used to fall back to the locale tree of the web console package,
 * deleted in PR #513. A default that points at a missing directory makes the rule
 * load zero keys and report zero problems, so the gate passes by reading nothing.
 * There are now three unrelated locale trees (packages/cli, private/account/web,
 * private/account) and no rule can guess which one a config block means, so the
 * option is required and the resolved path must be a real directory.
 *
 * @param {string} ruleName - Rule id, used in the error message
 * @param {string} optionName - Option key the caller must supply
 * @param {unknown} value - Raw option value
 * @param {string} projectRoot - Base for resolving relative values
 * @returns {string} Absolute, verified directory path
 */
export const resolveRequiredDirOption = (
  ruleName,
  optionName,
  value,
  projectRoot = process.cwd()
) => {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(
      `${ruleName}: the "${optionName}" option is required and must be a non-empty string. ` +
        `Set it explicitly in eslint.config.js, e.g. { ${optionName}: 'packages/cli/src/i18n/locales' }.`
    );
  }

  const absolute = path.isAbsolute(value) ? value : path.join(projectRoot, value);

  if (!fs.existsSync(absolute) || !fs.statSync(absolute).isDirectory()) {
    throw new Error(
      `${ruleName}: the "${optionName}" option resolves to "${absolute}", which is not an existing directory. ` +
        'A path that does not exist would make this rule read nothing and silently report no problems. ' +
        'Fix the path in eslint.config.js.'
    );
  }

  return absolute;
};
