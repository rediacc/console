# PLAN: Release-path protection -- deployment targets and build artifacts accept writes only from the trusted release path, while a local publish stays possible

Status: approved -- operator 2026-11-21, quoted under Ask; not before 2027-05-01
Depends-On: no-dep -- no box of another plan is a prerequisite; the work is deferred by date, not by another plan
Priority: P3 -- deferred by the operator until 2027-05; nothing in it blocks current work
Concurrency: parallel -- the boxes touch different settings and can run side by side once started
Owns: agent/plans/PLAN-release-path-protection-2027.md
Live-Proof: none -- planning record only until started, per the operator answer recorded in closed #f27cbf2d
Owner: d778be9d
First-Seen: 2026-11-21

## Ask

Operator, 2026-11-21, after a read-only review of the repository settings: "I want to be able to publish locally. No worries. Those ideal protection mechanisms should be handled. You can make a new plan to handle it after 2027-05. Keep it generic as much as possible. No code mention since code base could be different. Same answer for environments." <!-- style-ok -->

The answer covers both the build-artifact store and the deployment environments.

## Context (as observed on 2026-11-21, to be re-measured when the plan starts)

1. Build artifacts (container images used by CI) can be written by any workflow job that asks for write access, on any branch, because the repository holds full access to the artifact store through inheritance.
2. Deployment environments exist for every release channel and region, but allow any branch and carry no secrets, so today they gate nothing. Credentials live in an external secret manager.
3. Pull-request runs already write build artifacts only under a pull-request-scoped name that release runs never read, which closes the path for honest branch code. The remaining gap needs a malicious branch inside the repository.
4. Publishing from a developer machine is a supported release path and must keep working.

## Design

D1. One trusted release path per kind of write: a named identity (an automation app or a scoped token) is the only writer of release artifacts and deployments. Branch builds keep a read-only view.

D2. Environments are tied to the refs that really deploy (the main branch, release tags, the dispatch refs actually used), derived from the run history when the plan starts, never guessed.

D3. Local publishing uses the same trusted identity through the external secret manager, so a local release and a CI release are judged by one rule.

D4. Every restriction lands with a dry run first and a rollback note, and a release is run end to end on each restricted target before the next one is tightened.

## Risks

- A restriction that misses a real release path breaks a release. D2 and D4 exist for this.
- A new credential has to be rotated and kept out of logs. It lives only in the external secret manager.
- The code base and the hosting platform may have changed by 2027-05; the boxes describe outcomes, not files.

## Tasks

- [ ] P1 [lead] Re-measure the context: which identities can write build artifacts and deployments today, from which refs, and how a local publish authenticates. Record the findings in this plan before any change.
  Owns: none -- read-only survey of repository and platform settings.
  Depends on: none.
  Accept: a dated findings section in this plan, each claim with the page or command it came from.
- [ ] P2 [lead] Create the trusted release identity of D1 and D3, store it in the external secret manager, and move the release writes (CI and local) onto it, with branch builds left read-only.
  Owns: none -- chosen at start, once P1 names the current settings.
  Depends on: P1.
  Accept: a release from CI and a release from a local machine both publish through the new identity, and a branch build that tries to write a release artifact is refused (both recorded).
- [ ] P3 [lead] Tie each deployment environment to the refs P1 found really deploy (D2), one target at a time with a dry run and a rollback note (D4).
  Owns: none -- chosen at start.
  Depends on: P1.
  Accept: a release succeeds on every restricted target, and a run from an unlisted branch is refused by each environment (recorded per target).
- [ ] P4 [lead] Remove repository-wide write inheritance to the artifact store once P2 is proven, keeping the pull-request-scoped namespace for branch builds.
  Owns: none -- chosen at start.
  Depends on: P2.
  Accept: release runs and local publishes still write; a branch run writes only its own scoped namespace; recorded with dates.
