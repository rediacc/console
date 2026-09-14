# Web-vault steps: create `dev-shared`

Written 2026-09-09 for the operator. Everything below is web-vault only: verified today
that `bws` 2.1.0 has six verbs and no service-account verb, and `bw` 2026.8.0 exposes only
org item moves. Neither CLI can create a project or a machine account.

## Read this first: "bind all the same secrets to the new project" is not possible

Bitwarden's own docs are explicit: **"Each secret can only be associated with a single
project at a time."** So adding all 58 to `dev-shared` would MOVE them out of `ci-shared`,
and CI would lose every one of them the moment you saved -- `ci-readonly-console` has
access to `ci-shared`, not to the new project.

The good news is that the intent behind that request -- "nothing breaks while I decide" --
is achieved a different way, and more safely: **grant ACCESS to both projects, move
SECRETS one at a time.** A machine account can hold access to several projects; a secret
cannot live in several. Until a secret is moved, CI keeps reading it exactly as today.

## The five steps

1. **Create the project.** Secrets Manager -> Projects -> New project. Name it exactly
   `dev-shared` (the repo's spec spells it that way and a gate reads the string).

2. **Give the LOCAL account access to both.** Machine accounts -> `local-rw-account` ->
   Projects. It should list `ci-shared` AND `dev-shared`, both **Can read, write**.

3. **Leave the CI account alone, and check it.** Machine accounts ->
   `ci-readonly-console` -> Projects. It must list **`ci-shared` only**, **Can read**.
   This is the entire security win: CI becomes unable to SEE dev credentials, not merely
   unable to write them. If `dev-shared` appears here, remove it.

4. **Move exactly two secrets** into `dev-shared` -- open each, change Project, save:
   - `AWS_SES_ACCESS_KEY_ID`
   - `AWS_SES_SECRET_ACCESS_KEY`

   These two, and only these two, are what the repo's supply spec routes to `dev-shared`.
   Everything else is already correctly placed, is minted by the runner, is generated, or
   is a test fixture.

5. **Tell me when it is done** and I will re-run the probe: the map should still resolve
   58 names for `local-rw-account`, and the two above should now report `dev-shared`.

## Why those two, and the thing worth knowing before you move them

They are the sharp end of this whole exercise. In CI, `AWS_SES_ACCESS_KEY_ID` is a Worker
binding fed from the regional entry `AWS_SES_ACCESS_KEY_ID_EU`. On a developer machine the
same unsuffixed name sits in `private/account/.env` holding **the production EU key**.

So a developer machine currently carries a production credential under a name that reads
like a local one. Moving the pair to `dev-shared` does not fix that by itself -- it only
gives the right key somewhere to live. See the question below.

## What does NOT need doing

- No machine account needs minting. `local-rw-account` (never expires) and
  `ci-readonly-console` already exist and their `used_by` values already partition.
- No secret needs re-creating. Moving is an edit on the existing secret; the value is
  untouched and no consumer sees a gap.
- Nothing in this repo needs a code change first. The spec at
  `.ci/config/secret-supply.json` already encodes the destination, and its gate prints the
  blocked names on every run rather than failing.
