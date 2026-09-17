# PLAN: Fix garbled German translations in renet's de.go
Status: compacted Owner: w2d-writer Full-Text: f7a5351a9 agent/PLAN-fix-german-translation-artifacts.md Full-Text-Blob: 0ce3e39893deecb4e3e91cbfed5abdae0db3edd1 Record-Sig: 6e01a1c3

## Why
`private/renet/pkg/i18n/locales/de.go` carried machine-translation artifacts at scale: invented conjugations, stray English function words and untranslated English clauses spliced into German CLI strings. The plan enumerated them by PARSING both `en.go` and `de.go` and diffing per KEY rather than per line (the two files do not share line order), which put the real count at 423 of
2435 keys, well above the 150 to 200 a grep estimate had suggested.

## Outcome
SHIPPED, and it held. Header `done` is TRUE. Measured 2026-09-06.

- `private/renet/pkg/i18n/locales/de.go` is present at 2634 lines and the named artifact
tokens are gone: `albereit` and `Aufauflistenen` both return zero occurrences. The two surviving `Führe aus` hits (`:1049` `compose.run_running`, `:2372` `setup.run_sudo_renet_setup`) are correct German imperatives, not the fragment class the plan was hunting, and were checked individually rather than counted.
- The four sibling locales fixed in the same session are all still in the tree:
`fr.go`, `es.go`, `zh.go`, `ja.go`.
- THE STRONGEST EVIDENCE IS THE LATER GATE, which did not exist when this plan closed.
`private/renet/pkg/i18n/locale_quality_test.go` now enforces a shrink-only baseline (`TestLocaleQualityBaselineOnlyShrinks`) with an anti-vacuity control (`TestLocaleQualityGateCanFail`), and `locale_quality_baseline.json` holds 34 findings: 17+7+6 for `ru`, 3 for `ar`, 1 for `ko`, and ZERO for de, fr, es, zh or ja. The five locales this plan drained are the five the gate has
nothing baselined against.
- The renet-side commits are submodule commits and are not cited by sha here, because a
gitlink is not an object in this repository.

## Lessons
- RE-RUN THE DETECTOR AFTER THE FIX, not just against the calibration examples. The
423-line census undercounted by 29, and a second broader sweep is the only reason those 29 were not left behind as a silent tail.
- A census is a claim about a corpus, so it should be produced by parsing the corpus. The
grep estimate was off by a factor of two and would have set the wrong scope.
- Fixing one locale exposed the class: the same defect was found and drained in four more
locales in the same session, 1912 corrupted lines in total. Sweeping the class rather than the instance is what left the later quality gate with nothing to baseline here.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted Prior-Status: done Compacted-By: 8f55d4f0 Compacted-At: 2026-09-06T17:32:36Z Boxes: 0 attested, 0 open, 0 abandoned Epics: none Touched: none Gates: none Why-Source: author Read-History: `git show 0ce3e39893deecb4e3e91cbfed5abdae0db3edd1` recovers the text; `git log --find-object=0ce3e39893deecb4e3e91cbfed5abdae0db3edd1 --all` names the commit

## History
- 2026-09-06T17:32:36Z compacted by 8f55d4f0 from `done` (record-sig 6e01a1c3)
