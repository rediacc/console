import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockAccountServerFetch, mockGetSubscriptionTokenState } = vi.hoisted(() => ({
  mockAccountServerFetch: vi.fn(),
  mockGetSubscriptionTokenState: vi.fn(),
}));

vi.mock('../account/account-client.js', () => ({
  accountServerFetch: mockAccountServerFetch,
}));

vi.mock('../account/subscription-auth.js', () => ({
  getSubscriptionTokenState: mockGetSubscriptionTokenState,
}));

const {
  assertMachineSlotsAvailable,
  isMachineSlotLimitError,
  partialPlacementGuidance,
  readMachineSlotStatus,
} = await import('../account/license-preflight.js');

describe('machine-slot pre-flight', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'ready', token: { token: 'rdt' } });
    mockAccountServerFetch.mockResolvedValue({
      maxMachines: 5,
      activeMachineCount: 3,
      overLimitCount: 0,
    });
  });

  it('allows a placement that fits in the free slots', async () => {
    await expect(assertMachineSlotsAvailable({ machineCount: 2 })).resolves.toBeUndefined();
  });

  it('refuses a placement one machine too large, before anything is provisioned', async () => {
    await expect(assertMachineSlotsAvailable({ machineCount: 3 })).rejects.toThrow(
      /needs 3 more machine slot\(s\)/
    );
  });

  it('names the limit, the 5-hour float and the upgrade path in the refusal', async () => {
    // The three things an operator stuck at the wall can actually act on. A
    // bare "limit reached" leaves them with nothing but a support ticket.
    await expect(assertMachineSlotsAvailable({ machineCount: 9 })).rejects.toThrow(
      /5 hours.*upgrading the plan.*Enterprise or partner/s
    );
  });

  it('does not charge for machines that already hold a slot', async () => {
    // Re-running a placement that got part-way must not be refused for slots
    // its own earlier run already claimed.
    await expect(
      assertMachineSlotsAvailable({ machineCount: 4, alreadyActive: 3 })
    ).resolves.toBeUndefined();
  });

  it('stays silent when the numbers cannot be read', async () => {
    // Nobody signed in: the server still enforces the cap at issuance, so an
    // invented refusal here would block a run that would have succeeded.
    mockGetSubscriptionTokenState.mockReturnValue({ kind: 'missing' });
    await expect(assertMachineSlotsAvailable({ machineCount: 100 })).resolves.toBeUndefined();
    expect(mockAccountServerFetch).not.toHaveBeenCalled();
  });

  it('stays silent when the account server is unreachable', async () => {
    mockAccountServerFetch.mockRejectedValue(new Error('ECONNREFUSED'));
    await expect(assertMachineSlotsAvailable({ machineCount: 100 })).resolves.toBeUndefined();
  });

  it('stays silent against a server that does not report the fields', async () => {
    mockAccountServerFetch.mockResolvedValue({ subscriptionId: 'sub_1' });
    expect(await readMachineSlotStatus()).toBeNull();
    await expect(assertMachineSlotsAvailable({ machineCount: 100 })).resolves.toBeUndefined();
  });

  it('recognizes the server’s own cap refusal by code', () => {
    const error = Object.assign(new Error('Maximum machines (5) reached.'), {
      status: 403,
      code: 'MAX_MACHINES_REACHED',
    });
    expect(isMachineSlotLimitError(error)).toBe(true);
    expect(isMachineSlotLimitError(new Error('Maximum machines (5) reached.'))).toBe(false);
    expect(isMachineSlotLimitError(undefined)).toBe(false);
  });
});

describe('mid-provisioning failure state', () => {
  it('reports what exists, what never started, and the command to resume', () => {
    // The contract: nothing is rolled back. Destroying working deployments to
    // tidy up an accounting failure would be worse than the failure, and the
    // rollback would itself need slots to undo.
    const message = partialPlacementGuidance({
      placed: ['node-1', 'node-2'],
      remaining: ['node-3'],
      command: 'rdc repo replicate app --replicas 3',
    });

    expect(message).toContain('2 machine(s) completed (node-1, node-2)');
    expect(message).toContain('1 were never started (node-3)');
    expect(message).toContain('Nothing was rolled back');
    expect(message).toContain('rdc repo replicate app --replicas 3');
  });

  it('renders empty sides without a dangling separator', () => {
    const message = partialPlacementGuidance({
      placed: [],
      remaining: ['node-1'],
      command: 'rdc cluster create c1',
    });
    expect(message).toContain('0 machine(s) completed (-)');
  });
});
