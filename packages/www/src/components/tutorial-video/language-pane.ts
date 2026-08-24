import { getLanguageName, SUPPORTED_LANGUAGES } from '../../i18n/language-utils';
import type { Language } from '../../i18n/types';

/**
 * The site locale behind whatever tag a mount was given.
 *
 * `data-lang` can carry a full tag like `en-GB` while every locale list in this app holds
 * bare codes. Comparing the raw value marked the wrong entry as current and made every
 * later comparison wrong, so normalising is done once, here.
 */
export function baseLocale(tag: string): Language {
  const raw = tag.split('-')[0].toLowerCase();
  return ((SUPPORTED_LANGUAGES as readonly string[]).includes(raw) ? raw : 'en') as Language;
}

/**
 * Populate the `language` pane Plyr builds but does not fill.
 *
 * MODULE SCOPE, not a closure inside the effect. The component was over eslint's
 * `max-lines` and this function was most of the excess; hoisting it also drops the
 * effect's cognitive complexity back under the limit. It takes everything it needs, so
 * there is nothing to capture and nothing to keep in sync with a dependency array.
 *
 * Located by DOM id rather than through `player.elements.settings`, which Plyr's own
 * types do not declare. Every lookup is guarded and a miss returns false: if a Plyr
 * upgrade changes the id convention the row simply never appears and the caller keeps
 * the in-frame overlay up, so a viewer is never left with no picker at all.
 */
export function mountLanguagePane(opts: {
  video: HTMLVideoElement;
  controlClass: string;
  langs: Language[];
  active: Language;
  hasCaptions: boolean;
  onPick: (next: Language) => void;
}): boolean {
  const { video, controlClass, langs, active, hasCaptions, onPick } = opts;
  const root = video.closest('.plyr');
  const pane = root?.querySelector('[id^="plyr-settings-"][id$="-language"]');
  const list = pane?.querySelector('[role="menu"]');
  if (!root || !pane || !list) return false;

  const homeRows = root.querySelectorAll(
    '[id^="plyr-settings-"][id$="-home"] [role="menu"] > [role="menuitem"]'
  );
  const row = homeRows[(hasCaptions ? 1 : 0) + 1] as HTMLElement | undefined;
  if (row) {
    row.removeAttribute('hidden');
    // Plyr writes `data[type]` into this span and has no entry for ours, so without this
    // the row reads "Select language undefined".
    const valueSpan = row.querySelector('.plyr__menu__value');
    if (valueSpan) valueSpan.textContent = getLanguageName(active);
  }

  const items: HTMLButtonElement[] = [];
  for (const code of langs) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = `${controlClass} tvp-lang-item`.trim();
    item.setAttribute('role', 'menuitemradio');
    item.setAttribute('aria-checked', String(code === active));
    item.textContent = getLanguageName(code);
    item.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (code !== active) onPick(code);
    });
    list.appendChild(item);
    items.push(item);
  }

  // ArrowUp/Down roving focus, which Plyr writes for its own panes and not for ours.
  list.addEventListener('keydown', (ev) => {
    const e = ev as KeyboardEvent;
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    e.preventDefault();
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = e.key === 'ArrowDown' ? at + 1 : at - 1;
    items[(next + items.length) % items.length]?.focus();
  });
  return true;
}
