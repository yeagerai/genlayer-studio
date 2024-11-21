import { By, WebDriver } from 'selenium-webdriver';

import { SettingsPage } from '../pages/SettingsPage.js';
import { ContractsPage } from '../pages/ContractsPage.js';
import { before, describe, after, it } from 'node:test';
import { expect } from 'chai';
import { getDriver } from '../utils/driver.js';

let driver: WebDriver;
let settingsPage: SettingsPage;
let contractsPage: ContractsPage;

const providerParams = {
  provider: '0-custom-provider',
  model: '0-custom-model',
  plugin: 'openai',
};

const newApiKey = 'NEW_API_KEY';

describe('Settings - Manage Providers', () => {
  before(async () => {
    driver = await getDriver();
    settingsPage = new SettingsPage(driver);
    contractsPage = new ContractsPage(driver);
  });

  it('should create and update a custom provider', async () => {
    await contractsPage.navigate();
    await contractsPage.waitUntilVisible();
    await contractsPage.skipTutorial();

    await settingsPage.navigate();
    await settingsPage.waitUntilVisible();

    const initialProviders = await settingsPage.getProvidersElements();

    // Create
    await settingsPage.createCustomProvider(providerParams);

    const newProviders = await settingsPage.getProvidersElements();

    expect(
      newProviders.length,
      'number of providers should be one greather than old providers',
    ).be.equal(initialProviders.length + 1);

    const newProvider = await settingsPage.getFirstProviderWithModelText(
      providerParams.model,
    );

    expect(newProvider, 'newProvider should be found').to.exist;

    if (!newProvider) {
      throw new Error('newProvider not found');
    }

    // Update

    await newProvider.click();
    await driver.sleep(500);

    const apiKeyField = await driver.findElement(
      By.xpath("//input[@data-testid='config-field-api_key_env_var']"),
    );

    await apiKeyField.clear();
    await apiKeyField.sendKeys(newApiKey);

    const updateProviderBtn = await driver.findElement(
      By.xpath("//button[@data-testid='btn-update-provider']"),
    );

    await updateProviderBtn.click();
    await driver.sleep(500);

    await newProvider.click();

    const newApiKeyField = await driver.findElement(
      By.xpath("//input[@data-testid='config-field-api_key_env_var']"),
    );

    const newApiKeyFieldValue = await newApiKeyField.getAttribute('value');

    expect(
      newApiKeyFieldValue,
      'api key should be changed to the new value',
    ).to.equal(newApiKey);

    const newUpdateProviderBtn = await driver.findElement(
      By.xpath("//button[@data-testid='btn-update-provider']"),
    );

    await newUpdateProviderBtn.click();
    await driver.sleep(500);
  });

  it('should delete the custom provider', async () => {
    const existingProviders = await settingsPage.getProvidersElements();

    const existingProvidersLength = existingProviders.length;
    expect(
      existingProvidersLength,
      'number of providers should be greather than 0',
    ).be.greaterThan(0);

    const customProvider = existingProviders[0];

    if (!customProvider) {
      throw new Error('customProvider not found');
    }

    await driver.actions().move({ origin: customProvider }).perform();
    await driver.sleep(1000);

    const deleteProviderBtn = await customProvider.findElement(
      By.xpath("//button[@data-testid='provider-item-delete']"),
    );

    await deleteProviderBtn.click();
    await driver.sleep(1000);

    const confirmDeleteProviderBtn = await customProvider.findElement(
      By.xpath("//button[@data-testid='provider-item-confirm-delete']"),
    );

    await confirmDeleteProviderBtn.click();
    await driver.sleep(1000);

    const newProviders = await settingsPage.getProvidersElements();

    expect(
      newProviders.length,
      'providers length should be one less than initial providers length',
    ).be.equal(existingProvidersLength - 1);
  });

  after(() => driver.quit());
});
