// Real browser / real API. Set E2E_AUDIO to exercise processing and playback too.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

await mkdir('test-results', { recursive: true });
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
const context = await browser.newContext({ locale: 'ru-RU', viewport: { width: 1440, height: 1050 } });
const page = await context.newPage();
const errors = [], posts = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('request', (request) => { if (request.method() === 'POST') posts.push(request.url()); });
try {
  await page.goto(process.env.STUDIO_URL || 'http://127.0.0.1:5173');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru');
  await expect(page.getByRole('button', { name: 'Создать гармонию' })).toBeDisabled();
  await page.getByRole('button', { name: 'English', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await page.getByRole('button', { name: 'Switch to light theme' }).click();
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.getByLabel('Harmony output', { exact: false }).selectOption('vocal');
  await page.getByLabel('Audio input', { exact: false }).selectOption('vocals_only');
  await page.getByLabel('Harmony interval').selectOption('minor_third');
  await page.getByLabel('Pitch quantization').selectOption('chromatic');
  if (process.env.E2E_AUDIO) {
    await expect(page.getByText('Local engine connected')).toBeVisible({ timeout: 15000 });
    await page.getByLabel('Choose audio file').setInputFiles(resolve(process.env.E2E_AUDIO));
    await expect(page.getByRole('button', { name: 'Generate harmony', exact: true })).toBeEnabled();
    const pitchRequest = page.waitForRequest((request) => request.url().endsWith('/analyze-pitch'), { timeout: 120000 });
    await page.getByRole('button', { name: 'Generate harmony', exact: true }).click();
    await pitchRequest;
    await page.getByRole('button', { name: 'Русский', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Создаём гармонию…' })).toBeDisabled();
    await expect(page.getByText('Готово к прослушиванию').or(page.getByRole('heading', { name: 'Не удалось завершить создание гармонии' }))).toBeVisible({ timeout: 180000 });
    if (await page.getByRole('heading', { name: 'Не удалось завершить создание гармонии' }).count()) throw new Error(await page.getByRole('alert').innerText());
    expect(posts.filter((url) => url.endsWith('/upload'))).toHaveLength(1);
    expect(posts.filter((url) => url.endsWith('/render'))).toHaveLength(1);
    const track = page.locator('#results audio').nth(1);
    const handle = await track.elementHandle();
    await page.getByRole('button', { name: 'Воспроизвести: Второй вокальный голос', exact: true }).click();
    await expect.poll(() => track.evaluate((audio) => audio.currentTime)).toBeGreaterThan(0.1);
    const position = await track.evaluate((audio) => audio.currentTime);
    const url = await page.getByRole('link', { name: 'Вокал WAV', exact: true }).getAttribute('href');
    const before = posts.length;
    await page.getByRole('button', { name: 'English', exact: true }).click();
    expect(await track.evaluate((audio, original) => audio === original, handle)).toBe(true);
    expect(await track.evaluate((audio) => audio.currentTime)).toBeGreaterThanOrEqual(position);
    expect(await track.evaluate((audio) => audio.paused)).toBe(false);
    await expect(page.getByRole('link', { name: 'Vocal WAV', exact: true })).toHaveAttribute('href', url);
    await expect(page.getByLabel('Harmony volume')).toHaveValue('0.6');
    expect(posts.length).toBe(before);
    await page.getByRole('button', { name: 'Pause Vocal harmony', exact: true }).click();
    console.log('Real processing continued across language change; result, playing audio node, position, gains, and download URL preserved.');
  }
  for (const language of ['ru', 'en']) {
    await page.getByRole('button', { name: language === 'ru' ? 'Русский' : 'English', exact: true }).click();
    for (const theme of ['light', 'dark']) {
      if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('.theme-button').click();
      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 950 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await expect(page.getByRole('button', { name: 'Русский', exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: 'English', exact: true })).toBeVisible();
        await page.screenshot({ path: `test-results/locale-${language}-${theme}-${width}.png`, fullPage: true });
      }
      await expect(page.locator('html')).toHaveAttribute('lang', language);
    }
  }
  expect(errors).toEqual([]);
  console.log('RU browser detection, saved EN preference after reload, keyboard switching, and RU/EN × light/dark × 1440/390/320px layout checks passed.');
} finally { await browser.close(); }
