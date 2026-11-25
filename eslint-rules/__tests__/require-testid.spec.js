/**
 * custom/require-testid: the composite-root exemption.
 *
 * A Radix `Select` root renders no DOM element of its own, so a data-testid on it never reaches
 * the page; the `SelectTrigger` child is the element E2E tests reach. A root whose trigger child
 * carries the testid is covered by it. A root with neither still reports.
 */

export const ruleId = 'custom/require-testid';

const tsx = (body) => ({ code: `const C = () => (\n${body}\n);\n`, filename: 'test.tsx' });

export default async ({ sourceRuleTester, runCases }) => {
  const { default: requireTestId } = await import('../require-testid.js');

  return [
    runCases(sourceRuleTester(), ruleId, requireTestId, {
      valid: [
        // The trigger child carries the testid: the root is covered.
        tsx(
          '<Select value={v} onValueChange={f}>\n  <SelectTrigger data-testid="scope">\n    <SelectValue />\n  </SelectTrigger>\n</Select>'
        ),
        // A testid on the root itself still satisfies the rule.
        tsx('<Select data-testid="scope" value={v} />'),
        // A dynamic testid on the trigger counts too.
        tsx('<Select value={v}>\n  <SelectTrigger data-testid={"scope-" + k} />\n</Select>'),
      ],
      invalid: [
        // CONTROL: neither the root nor the trigger carries a testid.
        {
          ...tsx(
            '<Select value={v}>\n  <SelectTrigger>\n    <SelectValue />\n  </SelectTrigger>\n</Select>'
          ),
          errors: [{ messageId: 'missingTestId' }],
        },
        // CONTROL: a testid on an unrelated child does not cover the root.
        {
          ...tsx('<Select value={v}>\n  <SelectContent data-testid="list" />\n</Select>'),
          errors: [{ messageId: 'missingTestId' }],
        },
        // CONTROL: only a rootless composite is exempt; a `Modal` (required element) renders its own
        // DOM, so a testid on a `ModalTrigger` child does not cover it.
        {
          ...tsx('<Modal open={o}>\n  <ModalTrigger data-testid="x" />\n</Modal>'),
          errors: [{ messageId: 'missingTestId' }],
        },
      ],
    }),
  ];
};
