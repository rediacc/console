import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { protocolUrlService } from '../protocolUrlService';

// Mock the dynamic imports
vi.mock('../forkTokenService', () => ({
  createFreshForkToken: vi.fn().mockResolvedValue('mock-fork-token'),
}));

vi.mock('../apiConnectionService', () => ({
  apiConnectionService: {
    getApiUrl: vi.fn().mockResolvedValue('https://api.example.com/api'),
  },
}));

describe('ProtocolUrlService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('generateUrl', () => {
    it('generates basic protocol URL with required parameters', async () => {
      const url = await protocolUrlService.generateUrl({
        team: 'my-team',
        machine: 'my-machine',
        repository: 'my-repo',
      });

      expect(url).toContain('rediacc://');
      expect(url).toContain('my-team');
      expect(url).toContain('my-machine');
      expect(url).toContain('my-repo');
      expect(url).toContain('apiUrl=');
    });

    it('includes action in URL when specified', async () => {
      const url = await protocolUrlService.generateUrl({
        team: 'my-team',
        machine: 'my-machine',
        repository: 'my-repo',
        action: 'terminal',
      });

      expect(url).toContain('/terminal');
    });

    it('converts boolean query params to yes/no', async () => {
      const url = await protocolUrlService.generateUrl({
        team: 'my-team',
        machine: 'my-machine',
        repository: 'my-repo',
        queryParams: {
          autoExecute: true,
          popup: false,
        },
      });

      expect(url).toContain('autoExecute=yes');
      expect(url).toContain('popup=no');
    });

    it('handles empty repository gracefully', async () => {
      const url = await protocolUrlService.generateUrl({
        team: 'my-team',
        machine: 'my-machine',
        repository: '',
      });

      expect(url).toContain('rediacc://');
      expect(url).toContain('my-team');
      expect(url).toContain('my-machine');
    });

    it('URL-encodes special characters in parameters', async () => {
      const url = await protocolUrlService.generateUrl({
        team: 'my team',
        machine: 'my-machine',
        repository: 'my repo',
      });

      expect(url).toContain('my%20team');
      expect(url).toContain('my%20repo');
    });
  });

  describe('generateTerminalUrl', () => {
    it('generates terminal URL with terminal-specific params', async () => {
      const url = await protocolUrlService.generateTerminalUrl(
        {
          team: 'my-team',
          machine: 'my-machine',
          repository: 'my-repo',
        },
        {
          command: 'ls -la',
          autoExecute: true,
        }
      );

      expect(url).toContain('/terminal');
      expect(url).toContain('command=');
      expect(url).toContain('autoExecute=yes');
    });
  });

  describe('generateDesktopUrl', () => {
    it('generates desktop URL with container params', async () => {
      const url = await protocolUrlService.generateDesktopUrl(
        {
          team: 'my-team',
          machine: 'my-machine',
          repository: 'my-repo',
        },
        {
          containerId: 'abc123',
          action: 'terminal',
        }
      );

      expect(url).toContain('/desktop');
      expect(url).toContain('containerId=abc123');
    });
  });

  describe('generateVSCodeUrl', () => {
    it('generates VSCode URL with path param', async () => {
      const url = await protocolUrlService.generateVSCodeUrl(
        {
          team: 'my-team',
          machine: 'my-machine',
          repository: 'my-repo',
        },
        {
          path: '/src/main',
        }
      );

      expect(url).toContain('/vscode');
      expect(url).toContain('path=');
    });
  });

  describe('openUrl', () => {
    let windowOpenSpy: ReturnType<typeof vi.spyOn>;
    let addEventListenerSpy: ReturnType<typeof vi.spyOn>;
    let removeEventListenerSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
      addEventListenerSpy = vi.spyOn(window, 'addEventListener');
      removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.restoreAllMocks();
      vi.useRealTimers();
    });

    it('calls window.open with the protocol URL', async () => {
      const promise = protocolUrlService.openUrl('rediacc://test');
      vi.runAllTimers();
      await promise;

      expect(windowOpenSpy).toHaveBeenCalledWith('rediacc://test', '_self');
    });

    it('sets up blur event listener', async () => {
      const promise = protocolUrlService.openUrl('rediacc://test');
      vi.runAllTimers();
      await promise;

      expect(addEventListenerSpy).toHaveBeenCalledWith('blur', expect.any(Function));
    });

    it('resolves with success when blur event fires', async () => {
      const promise = protocolUrlService.openUrl('rediacc://test');

      // Simulate blur event
      const blurHandler = addEventListenerSpy.mock.calls.find(
        (call: [string, EventListener]) => call[0] === 'blur'
      )?.[1] as EventListener;

      if (blurHandler) {
        blurHandler(new Event('blur'));
      }

      const result = await promise;
      expect(result.success).toBe(true);
    });

    it('resolves with timeout error after 3 seconds', async () => {
      const promise = protocolUrlService.openUrl('rediacc://test');
      vi.runAllTimers();
      const result = await promise;

      expect(result.success).toBe(false);
      expect(result.error?.type).toBe('timeout');
    });

    it('handles window.open exceptions', async () => {
      windowOpenSpy.mockImplementation(() => {
        throw new Error('Popup blocked');
      });

      const result = await protocolUrlService.openUrl('rediacc://test');

      expect(result.success).toBe(false);
      expect(result.error?.type).toBe('exception');
      expect(result.error?.message).toContain('Popup blocked');
    });

    it('cleans up event listeners on timeout', async () => {
      const promise = protocolUrlService.openUrl('rediacc://test');
      vi.runAllTimers();
      await promise;

      expect(removeEventListenerSpy).toHaveBeenCalledWith('blur', expect.any(Function));
    });
  });

  describe('checkProtocolStatus', () => {
    let windowOpenSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      windowOpenSpy = vi.spyOn(window, 'open');
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.restoreAllMocks();
      vi.useRealTimers();
    });

    it('returns unavailable when popup is blocked', async () => {
      windowOpenSpy.mockReturnValue(null);

      const promise = protocolUrlService.checkProtocolStatus();
      vi.runAllTimers();
      const result = await promise;

      expect(result.available).toBe(false);
      expect(result.errorReason).toContain('Popup blocked');
    });

    it('detects protocol handler using navigation method', async () => {
      const mockWindow = {
        location: { href: 'about:blank' },
        close: vi.fn(),
      } as unknown as Window;

      windowOpenSpy.mockReturnValue(mockWindow);

      const promise = protocolUrlService.checkProtocolStatus();
      vi.runAllTimers();
      const result = await promise;

      expect(result.method).toBe('navigation');
      expect(mockWindow.close).toHaveBeenCalled();
    });
  });

  describe('checkProtocolAvailable', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('returns false after timeout', async () => {
      const promise = protocolUrlService.checkProtocolAvailable();
      vi.runAllTimers();
      const result = await promise;

      expect(result).toBe(false);
    });
  });

  describe('getInstallInstructions', () => {
    it('returns installation instructions for all platforms', () => {
      const instructions = protocolUrlService.getInstallInstructions();

      expect(instructions).toHaveLength(3);
      expect(instructions.map((i) => i.platform)).toEqual(['Windows', 'macOS', 'Linux']);
      expect(instructions.every((i) => i.instructions.length > 0)).toBe(true);
    });
  });

  describe('generateAllActionUrls', () => {
    it('generates URLs for all action types', async () => {
      const urls = await protocolUrlService.generateAllActionUrls({
        team: 'my-team',
        machine: 'my-machine',
        repository: 'my-repo',
      });

      expect(urls).toHaveProperty('navigate');
      expect(urls).toHaveProperty('terminal');
      expect(urls).toHaveProperty('desktop');
      expect(urls).toHaveProperty('vscode');
      expect(urls.terminal).toContain('/terminal');
      expect(urls.desktop).toContain('/desktop');
      expect(urls.vscode).toContain('/vscode');
    });
  });
});
