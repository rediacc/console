import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from '../../src/base/BasePage';

export class AuditPage extends BasePage {
  readonly filterCard: Locator;
  readonly filterDate: Locator;
  readonly filterEntity: Locator;
  readonly filterSearch: Locator;
  readonly refreshButton: Locator;
  readonly exportButton: Locator;
  readonly exportCsvOption: Locator;
  readonly exportJsonOption: Locator;
  readonly tableCard: Locator;
  readonly table: Locator;

  constructor(page: Page) {
    super(page, '/console/audit');
    this.filterCard = page.getByTestId('audit-filter-card');
    this.filterDate = page.getByTestId('audit-filter-date');
    this.filterEntity = page.getByTestId('audit-filter-entity');
    this.filterSearch = page.getByTestId('audit-filter-search');
    this.refreshButton = page.getByTestId('audit-refresh-button');
    this.exportButton = page.getByTestId('audit-export-button');
    this.exportCsvOption = page.getByTestId('audit-export-csv');
    this.exportJsonOption = page.getByTestId('audit-export-json');
    this.tableCard = page.getByTestId('audit-table-card');
    this.table = page.getByTestId('audit-table');
  }

  getPageLocators(): Record<string, Locator> {
    return {
      filterCard: this.filterCard,
      filterDate: this.filterDate,
      filterEntity: this.filterEntity,
      filterSearch: this.filterSearch,
      refreshButton: this.refreshButton,
      exportButton: this.exportButton,
      exportCsvOption: this.exportCsvOption,
      exportJsonOption: this.exportJsonOption,
      tableCard: this.tableCard,
      table: this.table,
    };
  }

  // Preset labels match common.json translations (e.g. "Last 7 Days", "Today").
  // RangePicker renders two inputs both with the same data-testid — use .first() to avoid strict mode.
  async selectDatePreset(presetLabel: string): Promise<void> {
    await this.filterDate.first().click();
    const presetItem = this.page.locator('.ant-picker-presets li').filter({ hasText: presetLabel });
    await presetItem.waitFor({ state: 'visible', timeout: 5000 });
    await presetItem.click();
    // Close the panel if the preset did not auto-dismiss it
    const panel = this.page.locator('.ant-picker-dropdown');
    if (await panel.isVisible().catch(() => false)) {
      await this.page.keyboard.press('Escape');
    }
  }

  async waitForDataLoaded(): Promise<void> {
    // Refresh button is enabled (not in loading state) once data is fetched
    await expect(this.refreshButton).toBeEnabled({ timeout: 15000 });
    await expect(this.tableCard).toBeVisible();
  }

  async selectEntityType(entityType: string): Promise<void> {
    await this.filterEntity.click();
    // Ant Design Select options: use content locator since aria-name may not match exactly
    const option = this.page
      .locator('.ant-select-item-option-content')
      .filter({ hasText: new RegExp(`^${entityType}$`) });
    await option.waitFor({ state: 'visible', timeout: 15000 });
    await option.click();
  }

  async clickRefresh(): Promise<void> {
    await this.refreshButton.click();
  }

  async triggerCsvExport(): Promise<void> {
    await this.exportButton.click();
    await this.exportCsvOption.waitFor({ state: 'visible', timeout: 5000 });
    await this.exportCsvOption.click();
  }
}
