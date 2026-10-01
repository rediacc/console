'use strict';
// The well-known values for CommonJS callers (github-script steps), read from
// the registry file itself: .ci/config/well-known.env is the only place they
// are written. Plain KEY=value lines; `#` lines and blanks are skipped.
const fs = require('node:fs');
const path = require('node:path');

const REGISTRY = path.resolve(__dirname, '../../.ci/config/well-known.env');

const load = () => {
  const out = {};
  for (const line of fs.readFileSync(REGISTRY, 'utf8').split('\n')) {
    const m = /^(WK_[A-Z0-9_]+)=(.*)$/.exec(line);
    if (m) out[m[1]] = m[2];
  }
  return out;
};

module.exports = load();
