/**
 * Ref parser for the P4 addressing grammar `repo[:tag][@place]` (spec/03 §2.1).
 *
 * A ref is a single addressable token that verbs share:
 *
 *     ref   := name [ ':' tag ] [ '@' place ]
 *     name  := label     (repo / datastore / machine / cluster / storage name)
 *     tag   := label     (fork tag; datastores reuse the same grammar)
 *     place := label     (a machine OR cluster name)
 *     label := /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/     (RFC-1123 DNS label)
 *
 * Repo names become auto-route subdomains and k8s namespace names, so the
 * charset is a strict DNS label: lowercase alphanumerics and hyphen, max 63, no
 * leading/trailing hyphen. `:` and `@` are STRUCTURAL separators, so they can
 * never appear inside a name/tag/place — the grammar forbids them (§2.1).
 *
 * The result is a struct every resolver consumes; nothing downstream string-
 * splits a ref again. A bare ref (`shop`) carries `tag: undefined`, which means
 * the reserved birth tag `base`: the resolver maps it through the family's grand
 * pointer, never by comparing the literal string `base` against stored keys.
 * Writing `:base` explicitly is refused with a teaching error.
 */

import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';

/** The reserved birth tag. A bare ref `shop` is exactly `shop:base`. */
export const RESERVED_TAG = 'base';

/** Maximum label length (RFC-1123 DNS label). */
export const LABEL_MAX_LENGTH = 63;

/** RFC-1123 DNS label: lowercase alphanumerics and hyphen, no edge hyphens. */
const LABEL_PATTERN = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;

export interface ParsedRef {
  /** The primary name (repo / datastore / machine / cluster / storage). */
  name: string;
  /**
   * The fork tag, or `undefined` for a bare ref. `undefined` means the reserved
   * birth tag `base`; resolvers map it through the family's grand pointer.
   */
  tag?: string;
  /** A machine or cluster name, present only when the ref carried `@place`. */
  place?: string;
}

type SegmentRole = 'name' | 'tag' | 'place';

const ROLE_LABEL: Record<SegmentRole, string> = {
  name: 'name',
  tag: 'tag',
  place: 'place',
};

function validationError(message: string): CliExitError {
  return new CliExitError(ERROR_CODES.VALIDATION_ERROR, message);
}

/** True when `value` is a well-formed RFC-1123 DNS label. */
export function isValidLabel(value: string): boolean {
  return LABEL_PATTERN.test(value);
}

/**
 * Validate one label segment, throwing an exit-2 error that names the concrete
 * defect (spec/03 §2.1: "the offending character named"). Callers that already
 * split on `:`/`@` never see those characters here; a `:`/`@` reaching this
 * function means it sat in a structurally illegal position (e.g. a tag after a
 * place), and the message names it.
 */
export function validateLabel(value: string, role: SegmentRole): void {
  const roleLabel = ROLE_LABEL[role];
  if (value.length === 0) {
    throw validationError(`the ${roleLabel} is empty; names may not be blank.`);
  }
  if (value.length > LABEL_MAX_LENGTH) {
    throw validationError(
      `the ${roleLabel} "${value}" is ${value.length} characters; names must be ${LABEL_MAX_LENGTH} characters or fewer.`
    );
  }
  const illegal = /[^a-z0-9-]/.exec(value);
  if (illegal) {
    throw validationError(
      `the ${roleLabel} "${value}" contains an illegal character '${illegal[0]}'; names may use lowercase letters, digits, and hyphens only.`
    );
  }
  if (value.startsWith('-') || value.endsWith('-')) {
    throw validationError(`the ${roleLabel} "${value}" must not start or end with a hyphen.`);
  }
}

/**
 * Validate a fork tag value (the `--tag` flag on `repo fork` / `cluster fork` /
 * `datastore fork`, and the explicit `:tag` in a ref). Enforces the label
 * grammar AND refuses the reserved `base` tag with the spec/03 §2.1 teaching
 * error.
 */
export function validateTag(value: string): void {
  if (value === RESERVED_TAG) {
    throw validationError('base names the original repository; pick another tag.');
  }
  validateLabel(value, 'tag');
}

/**
 * Parse `repo[:tag][@place]` into its struct, or throw an exit-2 CliExitError
 * naming the grammar violation. `@` binds looser than `:`, so a ref splits as
 * `(name[:tag])@place`; a `:` inside the place segment is therefore an illegal
 * character in a label, not a second tag.
 */
export function parseRef(input: string): ParsedRef {
  if (input.length === 0) {
    throw validationError('a reference is required, for example "shop".');
  }

  // Split off @place first — it binds looser than :tag.
  const atCount = (input.match(/@/g) ?? []).length;
  if (atCount > 1) {
    throw validationError(`"${input}" has more than one '@'; a reference names at most one place.`);
  }
  let namePart = input;
  let place: string | undefined;
  if (atCount === 1) {
    const atIdx = input.indexOf('@');
    namePart = input.slice(0, atIdx);
    place = input.slice(atIdx + 1);
    validateLabel(place, 'place');
  }

  // Split name[:tag].
  const colonCount = (namePart.match(/:/g) ?? []).length;
  if (colonCount > 1) {
    throw validationError(
      `"${namePart}" has more than one ':'; a reference names at most one tag.`
    );
  }
  let name = namePart;
  let tag: string | undefined;
  if (colonCount === 1) {
    const colonIdx = namePart.indexOf(':');
    name = namePart.slice(0, colonIdx);
    tag = namePart.slice(colonIdx + 1);
  }

  validateLabel(name, 'name');
  if (tag !== undefined) {
    // Reuses the base-tag refusal, so an explicit `:base` is rejected here too.
    validateTag(tag);
  }

  return { name, ...(tag !== undefined && { tag }), ...(place !== undefined && { place }) };
}
