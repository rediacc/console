## CI-overhaul closeout wave (session b9491d9c) -- updated ~18:15 local 2026-07-31

Full gap analysis of docs/ci-overhaul/ done; operator answered 4 questions:
1. D-1 GO-LIVE approved (next wave, branch 0731-2 off main af0da029f).
2. Wave C S1 shadow approved, sequenced AFTER the D-1 wave.
3. D-7 strict_required_status_checks_policy: FLIPPED TRUE on ruleset
   12344707 (verified on the PUT response). PRs must now be up to date
   with main before merge -- affects every future babysit round.
4. Loose ends riding the wave: v2 deferral issue (FILED: #548),
   submodule review bootstrap fix, E2E account-npm-trees cut. macOS
   demotion NOT selected (stays on the PR path).

Fable plan agent "d1-plan" is designing the wave (worklist #3be53088
leased). On its report: verify load-bearing claims, then implement
(max 2 writers, disjoint files), branch 0731-2, PR, babysit, merge on
operator ask. OPERATOR ACTION pending: widen CLAUDE_CODE_OAUTH_TOKEN
org secret to renet/account (token half of the review fix).

Still watching: tonight's ~04:20Z nightly = A5's last leg (worklist
[?] #b33ebca3, cron c24d7d13 checks after 04:30Z; green => close task
#9 + auto-closes issue #544). Mail channel OFF per operator (rotated
key); stop-hook v13/v14 stay local-only, never commit .claude/hooks/**.

## Next action
Read d1-plan's report when it lands; spot-check its file:line claims
against the tree; then implement the wave on 0731-2. If the nightly
window passes first, do the A5 check per the cron. Do not merge
anything unasked.
