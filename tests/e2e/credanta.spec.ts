import { expect, test, type Page } from 'playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const uploadDir = join(tmpdir(), 'credanta-playwright-fixtures');
const resumeText = [
  'Playwright Nurse',
  'Registered Nurse with travel nursing experience in ICU and telemetry.',
  'Managed patient education, care coordination, medication administration, and discharge planning.',
  'Collaborated with charge nurses and interdisciplinary teams to improve patient throughput.',
].join('\n');

function fixturePath(name: string, content: string): string {
  mkdirSync(uploadDir, { recursive: true });
  const path = join(uploadDir, `${runId}-${name}`);
  writeFileSync(path, content);
  return path;
}

function testAccount(label: string) {
  const safeLabel = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return {
    name: 'Playwright Nurse',
    email: `playwright-${safeLabel}-${runId}@example.com`,
    password: `Playwright-${safeLabel}-${runId}-Password!`,
  };
}

async function register(page: Page, account: ReturnType<typeof testAccount>) {
  await page.goto('/auth/register');
  await page.getByLabel('Name').fill(account.name);
  await page.getByLabel('Email').fill(account.email);
  await page.locator('#password').fill(account.password);
  await page.locator('#confirm_password').fill(account.password);
  await page.getByRole('button', { name: 'Create Account' }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.locator('.sidebar-user')).toContainText(account.email);
}

async function login(page: Page, account: ReturnType<typeof testAccount>) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(account.email);
  await page.locator('#password').fill(account.password);
  await page.getByRole('button', { name: 'Continue with Email' }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.locator('.sidebar-user')).toContainText(account.email);
}

async function logout(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).first().click();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole('heading', { name: 'Sign in to Credanta' })).toBeVisible();
}

async function uploadDocument(page: Page, title = 'Playwright RN Resume') {
  const filePath = fixturePath('resume.txt', resumeText);
  await page.goto('/documents/upload');
  await page.locator('#file').setInputFiles(filePath);
  await page.getByLabel(/Name/).fill(title);
  await page.locator('#category').selectOption('Other');
  await page.getByRole('button', { name: 'Save to vault' }).click();
  await expect(page).toHaveURL(/\/documents/);
  await expect(page.getByText(title)).toBeVisible();
}

test.describe.serial('Credanta core user journeys', () => {
  test('Registration', async ({ page }) => {
    await register(page, testAccount('registration'));
  });

  test('Login', async ({ page }) => {
    const account = testAccount('login');
    await register(page, account);
    await logout(page);
    await login(page, account);
  });

  test('Document Upload', async ({ page }) => {
    await register(page, testAccount('document-upload'));
    await uploadDocument(page);
  });

  test('Resume Enhancer', async ({ page }) => {
    await register(page, testAccount('resume-enhancer'));
    await page.goto('/premium/resume/enhance');
    await page.getByRole('button', { name: 'Paste text' }).click();
    await page.locator('#resume_text').fill(resumeText);
    await page.getByRole('button', { name: 'Use Standard Resume Enhancer' }).click();
    await expect(page.locator('#re-results')).toBeVisible();
    await expect(page.getByText('Resume Readiness Score')).toBeVisible();
    await expect(page.getByText('Choose a Resume Version')).toBeVisible();
  });

  test('Packet Generation', async ({ page }) => {
    await register(page, testAccount('packet-generation'));
    await uploadDocument(page, 'Playwright Packet Resume');
    const downloadPromise = page.waitForEvent('download');
    await page.evaluate(() => {
      window.location.href = '/packet';
    });
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/credentials-packet-\d{8}\.zip/);
  });

  test('Share Links', async ({ page }) => {
    await register(page, testAccount('share-links'));
    await uploadDocument(page, 'Playwright Share Resume');
    await page.goto('/share');
    await expect(page.getByRole('heading', { name: 'Share' })).toBeVisible();
    await page.getByLabel('Label').fill('Playwright Recruiter Link');
    await page.getByRole('button', { name: 'Create link' }).click();
    await expect(page).toHaveURL(/\/share/);
    await expect(page.getByText('Playwright Recruiter Link')).toBeVisible();
    await expect(page.locator('.share-link-box input')).toHaveValue(/\/s\//);
  });

  test('Mobile Navigation', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await register(page, testAccount('mobile-navigation'));
    const nav = page.getByRole('navigation', { name: 'Main navigation' }).last();
    await expect(nav).toBeVisible();
    await nav.getByText('Portfolio').click();
    await expect(page).toHaveURL(/\/documents/);
    await nav.getByText('Upload').click();
    await expect(page).toHaveURL(/\/documents\/upload/);
    await nav.getByText('Account').click();
    await expect(page).toHaveURL(/\/account/);
  });

  test('Logout', async ({ page }) => {
    await register(page, testAccount('logout'));
    await logout(page);
  });
});
