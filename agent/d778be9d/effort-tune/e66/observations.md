# Effort tuner observations, session d778be9d, context epoch 66

Written by the session before it spawns the effort-tuner agent: the checks this context found
useful or useless and why, and any judge errors seen. One line per check key.

## Useful

## Useless

## Judge errors

- judge: repeatedly demanded a full status roster at effort smart; judge-threshold fix 19f83adaa now routes that to advisories (judge error, fixed).
- open-items: useful; the block led to real work (items closed or re-leased).
- ladder-gone (leased to a finished worker): useful; led to real work (re-leased).
- defer-expired: useless in this case; fired on a time-gated deferral (#c33b8946, cannot apply before a fixed UTC time) with no honest action; hint filed proposing a not-before field.
- stats filter bug fixed in 35d72a15d had hidden 8 of 12 rows on the first run.
