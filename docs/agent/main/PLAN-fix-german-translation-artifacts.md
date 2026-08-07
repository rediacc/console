# PLAN: Fix garbled German translations in renet's de.go
Status: done
Owner: w2d-writer
Updated: 2026-08-04

## Outcome (2026-08-04)

Implemented in full. 452 lines fixed in `de.go` (423 from the original census plus
29 more found by a second, broader sweep the census had missed — see below).
Verified: `gofmt -l` clean, `go build ./...` clean, `go test ./pkg/i18n/...` passes
(pre-existing failure in the same package is scoped entirely to `ru.go` /
`locale_quality_test.go`, a different concurrent teammate's in-flight work — zero
overlap with this fix), `go run ./cmd/renet i18n validate --format=json` reports
`missingCount=0`/`orphanCount=0` for `de`, format-verb parity exact for all 452
touched keys, zero new em dashes/curly quotes, every changed diff line is a
value-only edit.

**The 423-line census undercounted by 29.** Re-running a broader detector after
the first fix pass (matching stray English words plus a few tokens the first
census's classification missed, e.g. `albereit` in contexts other than the ones
already caught, `Aufauflistenen` on `cmd.list_*`/`*_list_short` variants, `Führe
aus` fragments) found 29 more corrupted lines the plan's enumeration did not
list. Fixed those too. Lesson for next time: re-run the detector after the fix,
not just against the calibration examples — a partial census silently leaves a
tail behind.

**Discovered while checking the class of bug elsewhere in the same campaign:** the
identical defect class (English words/phrases spliced into non-English CLI
locale strings, invented verb blends, English word order kept) was also found
and fixed in the same session, across the whole `pkg/i18n/locales/` tree:
`fr.go` (322 lines), `es.go` (211 lines), `zh.go` (354 lines), `ja.go` (573
lines) — via two disjoint writer sub-agents (fr+es, zh+ja), each independently
verified with the same suite as de.go (gofmt, go build, go test, i18n validate,
format-verb parity, em-dash grep). Total across all five locales: 1912 corrupted
lines fixed. `renet i18n validate` and the pre-existing hardcoded-string gate
(`i18n.sh`) both stay green throughout, modulo the 2 pre-existing/expected
`pkg/infra/docker/service.go` findings unrelated to locales.

Final verification (2026-08-04, all five files together):
`gofmt -l pkg/i18n/locales/*.go` clean, `go build ./...` exit 0,
`go test ./pkg/i18n/...` — key-parity/format-parity tests pass (a separate,
unrelated failure in the same package, `TestLocaleValuesAreTranslated`, is
scoped entirely to `ru.go` + an untracked `locale_quality_test.go` from a
different concurrent teammate's in-flight work — confirmed zero overlap with
any of the five files this plan touched), `i18n validate --format=json` reports
`missingCount=0`/`orphanCount=0` for de/fr/es/zh/ja, `i18n validate
--check-hashes` reports up-to-date.

## 0. Scope and method

This plan enumerates every `message.SetString(tag, "KEY", "VALUE")` line in
`private/renet/pkg/i18n/locales/de.go` whose `VALUE` contains a machine-translation
artifact (invented conjugation, stray English function word, or an untranslated
English clause), verified by parsing the actual file content (2435 keys, 1:1 key-parity
with `en.go`) and diffing each `de` value against its `en` counterpart by key (not by
line number — the two files do not share line order).

**Total corrupted lines found: 423** (out of 2435 `SetString` calls, ~17.4%). This is
higher than the "150-200" figure in the original report, which was a rough grep
estimate; this enumeration is exhaustive (parse of both files + per-key diff +
heuristic classification, spot-checked against `en.go`).

### Verification-gate caveat

`private/renet/pkg/i18n/rules.go` already implements a detector
(`detectEnglishFragments`, `detectWordBlends`, `detectFormatParity`) wired to
`renet i18n validate`. It reports `suspectedCount: 0` and `parityCount: 0` for `de`
TODAY, i.e. it is blind to all 423 lines below, for two reasons:

1. `rules.go`'s `localeHomographs["de"]` list wrongly includes `to`, `of`, `is`, `not`,
   `must`, `the`, `at`, `be`, `are`, `do` as "legitimate German homographs" — none of
   these are real German words (only `war`, `was`, `will`, `man`, `hat`, `so` are).
   This over-broad list suppresses `detectEnglishFragments` for exactly the
   stray-word corruption this report is about.
2. `detectWordBlends` only inspects non-ASCII tokens (built for scripts like
   Turkish/Chinese where a blend produces a mixed-script token). German is
   Latin-script, so invented blends like `Starteing`, `Installiereing`, `erstelled`
   are pure ASCII and structurally invisible to that rule too.

Net effect: the automated gate shows 0 defects for `de` both before and after this
fix, so it cannot be the sole verification signal (see §5). This is a pre-existing
gap in `rules.go`, out of scope for this content-only fix — filed as a follow-up
worklist item, not fixed here.

## 1. Root-cause groups

- **Group A — `erfolgfully` adverb blend** (67 lines): "successfully" split into
  "success" + "-fully", stem translated (`Erfolg`), English adverb morpheme
  reattached literally. Fix: `erfolgreich`, placed BEFORE the participle per house
  style (`executor.function_completed_successfully` = `"%s erfolgreich
  abgeschlossen"`).
- **Group B — invented verb/participle blends** (~140 unique lines, 195 token-hits):
  `-ing` stapled onto a German stem (`Starteing`, `Installiereing`, `Stoppeping`,
  `ausning`, `aufing`, `neueing`, `Erstelleing`, `Ladeing`, `Kopiereing`,
  `Uninstalliereing`, `Registriereing`, `Upladeing`, `Downladeing`,
  `Synchronisiereing`, `Protokollging`, `Aufauflistenening`, `abrufing`); `-ed`
  stapled onto a German stem (`erstelled`, `lösched`, `regrößed`, `installiereed`,
  `starteed`, `stoppeped`, `neueed`, `ladeed`); adjective blend `integritäty` for
  "healthy". House style for progressives is the German `wird + Partizip` passive
  (`msg.ceph.pool.creating` = `"Pool '%s' wird erstellt..."`), not a literal
  "un-blended" gerund (German has none).
- **Group C — stray English function words spliced into a German clause**
  (~210 unique lines, 231 token-hits): `for`(85), `to`(65), `be`(27), `is`(26),
  `all`(25), `not`(21), `found`(11), `skipping`(9), `available`(6), `after`(5),
  `if`(4), `integrity`(3), `than`(2), `are`(2), `before`(1), `fully`(1). Dominant
  template: `"Warte for X to be bereit..."` → `"Warte, bis X bereit ist..."`.
- **Group D — whole English clauses barely touched** (25 lines): English sentence
  structure kept, one noun swapped for a German word (`Shutting down erstelle
  VM...`, `Destroying netzwerk %s...`).
- **Group E — over-translated proper nouns/identifiers** (cross-cutting, high
  caution): `Rediaccfile` → `Rediaccdatumi` (must stay verbatim, it's this repo's
  literal config-file term); `UpdateMachineStatus` → `AktualisiereMaschineStatus`
  (literal RPC method name, must stay verbatim). Related noun-blend corruptions:
  `datumi`/`datumisystem` should be `Datei`/`Dateisystem`, `gerät`→`Gerät`,
  `netzwerk`→`Netzwerk`, `knotens`→`Knoten` (invariant plural), `arbeiters`→
  `Arbeiter` (invariant plural), `topoprotokolly`→`Topologie`.

## 2. Namespace breakdown (45 namespaces affected)

`cmd` 45, `infra` 45, `ceph` 43, `orchestration` 40, `setup` 33, `ops` 32,
`daemon` 18, `repository` 18, `proxy` 17, `service` 14, `provisioner` 13,
`compose` 12, `system` 10, `setup_command` 9, `datastore` 7, `resize_workflows` 7,
`worker` 7, `vm` 5, `msg` 4, `orchestrator` 4, `status` 4, `driver` 3,
`rediaccfile` 3, `repository_mount` 3, and 9 more with 1-2 each (`dns, install,
loopback, mesh, repository_create, repository_delete, repository_unmount,
repository_validate, router, builder, docker, error, helpers, kvm, lifecycle,
network, repository_resize, server`).

## 3. Calibration examples

1. `ops.up_vm_already_running_skipping` (the originally-reported bug) —
   `"VM %d albereit führe ausning, skipping"` → `"VM %d läuft bereits, wird
   übersprungen"`
2. `ceph.cluster_destroy_success` — `"Cluster destroyed erfolgfully"` →
   `"Cluster erfolgreich zerstört"`
3. `ceph.install_installing` — `"Installiereing Ceph prerequisites..."` →
   `"Ceph-Voraussetzungen werden installiert..."`
4. `daemon.cleaning_ips` — `"Räume aufing up unused loopback IPs for netzwerk
   %d..."` → `"Nicht verwendete Loopback-IPs für Netzwerk %d werden
   aufgeräumt..."`
5. `ceph.provisioner.cluster_healthy` — `"Ceph cluster is integritäty!"` →
   `"Ceph-Cluster ist gesund!"`
6. `cmd.create_ops_vmcmd_waiting_for_vm_to` — `"Warte for VM to be bereit..."` →
   `"Warte, bis die VM bereit ist..."` (applied to all `Warte for X to be bereit`
   siblings)
7. `infra.image_shutting_down_vm` — `"Shutting down erstelle VM..."` →
   `"Build-VM wird heruntergefahren..."`
8. `orchestration.rediaccfile_down_no_files` — `"No Rediaccdatumis found,
   skipping down phase"` → `"Keine Rediaccfiles gefunden, Down-Phase wird
   übersprungen"` (product term `Rediaccfile` kept verbatim)
9. `status.api_calling` — `"Calling AktualisiereMaschineStatus API"` →
   `"Aufruf der UpdateMachineStatus-API"` (RPC name kept verbatim)

## 4. Full enumeration

All 423 `file:line | key | groups | current(broken) | english-source` rows are
recorded in the Plan agent's working notes and were used directly to drive the
fix; the fix itself (the diff on `de.go`) is the durable record of the full
enumeration once applied.

## 5. Verification plan

1. Re-run the classification (parse both files, diff by key, apply groups A-D
   heuristics) and confirm 0 findings remain — not just the calibration examples.
2. `cd private/renet && go test ./pkg/i18n/...` — key-parity and format-parity
   tests must stay green before and after.
3. `go run ./cmd/renet i18n validate --format=json` — confirms `missingCount=0`,
   `orphanCount=0` for `de` post-fix (the `suspectedCount`/`parityCount` caveat
   from §0 still applies — a green result there was already true before the fix
   too, so it is not proof of the fix, just of no structural breakage).
4. `go build ./...` from `private/renet/` as a Go-syntax sanity check (per repo
   CLAUDE.md, bare `go build` is fine for `pkg/i18n` value-only edits; only the
   full embedded-asset binary build needs `build.sh`).
5. `gofmt -l private/renet/pkg/i18n/locales/de.go` should produce no output.
6. Grep for zero em dashes / curly quotes / non-breaking spaces introduced
   (the file legitimately uses `→` in one string; don't blanket-reject all
   non-ASCII).
7. Per touched line, `%s`/`%d`/`%v` format-verb count must match `en.go` exactly.
8. `git diff` must show only value-string changes — key names (`"KEY",`) must be
   byte-identical between `-` and `+` lines.
9. Out of scope, filed separately: `rules.go`'s German homograph allowlist is
   over-broad and `detectWordBlends` is ASCII-blind, so this class of bug can
   recur silently without a `rules.go` fix. Not fixed here (different file,
   different owner scope) — flagged to the campaign lead.

### Critical files
- private/renet/pkg/i18n/locales/de.go (the fix)
- private/renet/pkg/i18n/locales/en.go (reference, read-only)
- private/renet/pkg/i18n/rules.go (gate gap, NOT touched by this plan)
