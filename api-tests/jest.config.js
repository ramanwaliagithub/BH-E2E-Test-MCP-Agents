module.exports = {
  testEnvironment: 'allure-jest/node',
  testEnvironmentOptions: {
    resultsDir: 'allure-results',
  },
  testMatch: ['**/tests/*\.test\.js', '!**/tests/*.additional.test.js'],
  collectCoverageFrom: ['**/*.js', '!node_modules/**', '!coverage/**'],
  coverageThreshold: {
    global: {
      branches: 50,
      functions: 50,
      lines: 50,
      statements: 50,
    },
  },
  verbose: true,
  testTimeout: 30000,
};
