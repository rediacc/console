/**
 * Review 769b0a28.3: the pt locale is written in European Portuguese ("utilizador"), and four new keys arrived in Brazilian "usuário".
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const BRAZILIAN_USER = /usu[aá]rio/i;

describe('pt cli locale register', () => {
  it('control: the check recognises the Brazilian word', () => {
    expect(BRAZILIAN_USER.test('O usuário não confirmou')).toBe(true);
    expect(BRAZILIAN_USER.test('O utilizador não confirmou')).toBe(false);
  });

  const LOCALES = [
    '../i18n/locales/pt/cli.json',
    '../../../shared/src/cli-contract/data/i18n/pt.json',
  ] as const;
  for (const rel of LOCALES) {
    it(`names the user "utilizador" in every string of ${rel.split('/').slice(-3).join('/')}`, () => {
      const text = readFileSync(resolve(import.meta.dirname, rel), 'utf-8');
      const hits = text.split('\n').filter((line) => BRAZILIAN_USER.test(line));
      expect(hits.map((line) => line.trim().slice(0, 60))).toEqual([]);
    });
  }
});
