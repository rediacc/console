# Follow-up structural proof for three locale-sync commits

Checked 2026-11-28 by comparing each commit with its parent (`git show <c>:<path>` against `<c>^:<path>`):

| commit | files | JSON parsed | JSON keys lost | markdown pages | heading count differs from English |
|---|---|---|---|---|---|
| d3c89437e4 | 26 | 14 | 0 | 12 | 0 |
| f6391841c7 | 38 | 14 | 0 | 24 | 0 |
| 4d65781eac | 54 | 41 | 0 | 13 | 0 |
