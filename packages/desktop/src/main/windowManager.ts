import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { app, BrowserWindow, screen } from 'electron';

interface WindowState {
  width: number;
  height: number;
  x?: number;
  y?: number;
  isMaximized?: boolean;
}

export class WindowManager {
  private readonly statePath: string;
  private state: WindowState = { width: 1280, height: 800 };

  constructor() {
    this.statePath = join(app.getPath('userData'), 'window-state.json');
  }

  loadState(): WindowState {
    try {
      if (existsSync(this.statePath)) {
        const data = readFileSync(this.statePath, 'utf-8');
        this.state = JSON.parse(data) as WindowState;

        // Validate that window is visible on a display
        const displays = screen.getAllDisplays();
        const isVisible = displays.some((display) => {
          const { x, y, width, height } = display.bounds;
          return (
            this.state.x !== undefined &&
            this.state.y !== undefined &&
            this.state.x >= x - 100 && // Allow some tolerance
            this.state.x < x + width &&
            this.state.y >= y - 100 &&
            this.state.y < y + height
          );
        });

        // Reset position if window would be off-screen
        if (!isVisible) {
          delete this.state.x;
          delete this.state.y;
        }
      }
    } catch (error) {
      console.error('Failed to load window state:', error);
      // Use defaults on error
    }
    return this.state;
  }

  track(window: BrowserWindow): void {
    const saveState = (): void => {
      if (!window.isMinimized() && !window.isMaximized()) {
        const bounds = window.getBounds();
        this.state = {
          width: bounds.width,
          height: bounds.height,
          x: bounds.x,
          y: bounds.y,
          isMaximized: false,
        };
      }
      this.state.isMaximized = window.isMaximized();
    };

    // Debounce save operations
    let saveTimeout: NodeJS.Timeout | null = null;
    const debouncedSave = (): void => {
      if (saveTimeout) clearTimeout(saveTimeout);
      saveTimeout = setTimeout(saveState, 100);
    };

    window.on('resize', debouncedSave);
    window.on('move', debouncedSave);
    window.on('maximize', saveState);
    window.on('unmaximize', saveState);

    window.on('close', () => {
      if (saveTimeout) clearTimeout(saveTimeout);
      saveState();
      this.saveToFile();
    });
  }

  private saveToFile(): void {
    try {
      const dir = app.getPath('userData');
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true });
      }
      writeFileSync(this.statePath, JSON.stringify(this.state, null, 2));
    } catch (error) {
      console.error('Failed to save window state:', error);
    }
  }
}
