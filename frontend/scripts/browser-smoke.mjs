// Real browser checks. No API interception or synthetic production responses.
// Optional E2E_AUDIO runs the complete installed backend pipeline with that file.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

await mkdir('test-results', { recursive: true });
const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true });
const page = await browser.newPage({ locale: 'en-US', viewport: { width: 1440, height: 1100 } });
const errors = [];
const inputMode = process.env.E2E_INPUT_MODE || 'full_song';
const outputMode = process.env.E2E_OUTPUT_MODE || 'piano';
const vocal = outputMode === 'vocal';
const direction = process.env.E2E_DIRECTION || 'above';
page.on('pageerror', (error) => errors.push(error.message));
try {
  await page.goto(process.env.STUDIO_URL || 'http://127.0.0.1:5173');
  await expect(page.getByRole('heading', { name: /One melody/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Generate harmony' })).toBeDisabled();
  await expect(page.getByLabel('Pitch quantization')).toBeDisabled();
  await page.getByLabel('Harmony interval').selectOption('perfect_fifth');
  await expect(page.getByLabel('Pitch quantization')).toBeEnabled();
  await page.getByLabel('Harmony interval').selectOption('diatonic_third');
  await expect(page.getByLabel('Harmony volume')).toHaveValue('8');
  await page.getByRole('button', { name: 'Balanced', exact: true }).click();
  await expect(page.getByLabel('Harmony volume')).toHaveValue('4');
  await page.getByRole('button', { name: 'Harmony Forward', exact: true }).click();
  await expect(page.getByLabel('Musical key')).toHaveValue('');
  await page.getByLabel('Audio input', { exact: false }).selectOption('vocals_only');
  await expect(page.getByText(/Separation bypassed/)).toBeVisible();
  await page.getByLabel('Harmony output', { exact: false }).selectOption('vocal');
  await expect(page.getByText(/Above and Below have sounded robotic/)).toBeVisible();
  await expect(page.getByLabel('Harmony volume')).toHaveValue('0.6');
  await page.screenshot({ path: 'test-results/studio-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/studio-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.getByLabel('Audio input', { exact: false }).selectOption(inputMode);
  await page.getByLabel('Harmony output', { exact: false }).selectOption(outputMode);
  // A fixed chromatic interval needs no unverified song-key assumption.
  await page.getByLabel('Harmony interval').selectOption('minor_third');
  await page.getByLabel('Pitch quantization').selectOption('chromatic');
  await page.getByRole('button', { name: direction === 'below' ? 'Below melody' : 'Above melody' }).click();
  if (process.env.E2E_AUDIO) {
    await expect(page.getByText('Local engine connected')).toBeVisible({ timeout: 15_000 });
    await page.getByLabel('Choose audio file').setInputFiles(resolve(process.env.E2E_AUDIO));
    await expect(page.getByRole('button', { name: 'Generate harmony' })).toBeEnabled({ timeout: 15_000 });
    const rendered = page.waitForResponse((response) => response.url().endsWith('/render'), { timeout: 1_200_000 });
    await page.getByRole('button', { name: 'Generate harmony' }).click();
    await expect(page.getByRole('button', { name: 'Creating your harmony…' })).toBeDisabled();
    // Fail early with the real API error, otherwise wait for the final results.
    await expect(page.getByText('Ready to play').or(page.getByRole('heading', { name: 'We couldn’t finish this harmony' }))).toBeVisible({ timeout: 1_200_000 });
    if (await page.getByRole('heading', { name: 'We couldn’t finish this harmony' }).count()) throw new Error(await page.getByRole('alert').innerText());
    const renderResponse = await rendered;
    expect(JSON.parse(renderResponse.request().postData())).toEqual(vocal
      ? { velocity: 90, output_mode: 'vocal', instrumental_gain: 0.85, lead_vocal_gain: 0.7, harmony_gain: 0.6 }
      : { velocity: 90, instrumental_gain: 0.85, lead_vocal_gain: 0.4, harmony_gain: 8 });
    const renderData = await renderResponse.json();
    expect(renderData.mix_diagnostics.mode).toBe('stems');
    expect(renderData.mix_diagnostics.output.clipping_risk).toBe(false);
    expect(renderData.mix_diagnostics.gained_levels.harmony.rms).toBeGreaterThan(0);
    if (vocal) await expect(page.getByRole('link', { name: 'MIDI', exact: true })).toHaveCount(0);
    for (const label of (vocal ? ['Vocal WAV', 'Preview WAV'] : ['MIDI', 'Piano WAV', 'Preview WAV'])) {
      const url = await page.getByRole('link', { name: label, exact: true }).getAttribute('href');
      const response = await page.request.get(new URL(url, page.url()).href);
      expect(response.status()).toBe(200);
      const data = await response.body();
      expect(data.subarray(0, 4).toString()).toBe(label === 'MIDI' ? 'MThd' : 'RIFF');
      expect(data.length).toBeGreaterThan(44);
    }
    const preview = page.locator('#results audio').last();
    await page.getByRole('button', { name: 'Play Preview mix', exact: true }).click();
    await expect.poll(() => preview.evaluate((audio) => audio.currentTime)).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Pause Preview mix', exact: true }).click();
    await page.getByRole('button', { name: vocal ? 'Play Vocal harmony' : 'Play Piano harmony', exact: true }).click();
    await expect.poll(() => page.locator('#results audio').nth(1).evaluate((audio) => audio.currentTime)).toBeGreaterThan(0);
    await page.screenshot({ path: `test-results/studio-${inputMode}-${outputMode}-${direction}.png`, fullPage: true });
    console.log(JSON.stringify({ audio_id: renderData.audio_id, inputMode, outputMode, direction, diagnostics: renderData.mix_diagnostics }));
    console.log('Real backend pipeline, mode-specific downloads, and harmony/preview playback passed.');
  }
  expect(errors).toEqual([]);
  console.log('Desktop/mobile layout, settings, button validation, and browser runtime checks passed.');
} finally {
  await page.screenshot({ path: 'test-results/studio-last-state.png', fullPage: true }).catch(() => {});
  await browser.close();
}
