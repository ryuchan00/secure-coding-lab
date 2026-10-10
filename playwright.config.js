const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  workers: 1,
  fullyParallel: false,
  timeout: 30000,
  use: { baseURL: 'http://localhost:8080', viewport: { width: 1512, height: 982 }, trace: 'retain-on-failure' },
});
