/* eslint-env node */
require('@rushstack/eslint-patch/modern-module-resolution');

module.exports = {
  root: true,
  extends: [
    'plugin:vue/vue3-essential',
    'eslint:recommended',
    '@vue/eslint-config-typescript',
    '@vue/eslint-config-prettier/skip-formatting',
  ],
  rules: {
    'vue/multi-word-component-names': 'off',
  },
  overrides: [
    {
      files: [
        'tests/e2e/**/*.{cy,spec}.{js,ts,jsx,tsx}',
        'tests/support/**/*.{js,ts,jsx,tsx}',
      ],
    },
  ],
  parserOptions: {
    ecmaVersion: 'latest',
  },
};
