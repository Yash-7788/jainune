const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { validateReleaseConfig } = require('../scripts/release-config.cjs');
const { addSecurityPod } = require('../plugins/securityPod');

function loadTs(file, mocks, env = {}, dev = false) {
  const source = fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
  }}).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    exports, module: { exports }, process: { env }, __DEV__: dev, global: {},
    console, setTimeout, clearTimeout,
    require(name) {
      if (name in mocks) return mocks[name];
      throw new Error(`Unexpected dependency: ${name}`);
    },
  });
  return exports;
}

test('release rejects missing/insecure/mixed endpoints and development mocks', () => {
  const valid = { EXPO_PUBLIC_API_URL: 'https://api.jainune.com/v1', EXPO_PUBLIC_WS_URL: 'wss://api.jainune.com/v1/ws/chat' };
  assert.deepEqual(validateReleaseConfig(valid), []);
  for (const changes of [{ EXPO_PUBLIC_API_URL: '' }, { EXPO_PUBLIC_API_URL: 'http://localhost:8000/v1' },
    { EXPO_PUBLIC_WS_URL: 'wss://staging.jainune.com/v1/ws/chat' }, { EXPO_PUBLIC_USE_MOCKS: 'true' },
    { EXPO_PUBLIC_API_URL: 'https://user:password@api.jainune.com/v1' }]) {
    assert.ok(validateReleaseConfig({ ...valid, ...changes }).length > 0);
  }
});

test('REST and chat share local and staging environments', () => {
  for (const [platform, api] of [['android', 'http://10.0.2.2:8000/v1'], ['ios', 'http://localhost:8000/v1']]) {
    const endpoints = loadTs('src/config/endpoints.ts', { 'react-native': { Platform: { OS: platform } } }, {}, true);
    assert.equal(endpoints.API_BASE_URL, api);
    assert.equal(endpoints.WS_BASE_URL, `${api.replace(/^http/, 'ws')}/ws/chat`);
  }
  const endpoints = loadTs('src/config/endpoints.ts', { 'react-native': { Platform: { OS: 'ios' } } }, {
    EXPO_PUBLIC_API_URL: 'https://staging.jainune.com/v1/',
  });
  assert.equal(endpoints.WS_BASE_URL, 'wss://staging.jainune.com/v1/ws/chat');
});

test('iOS plugin preserves native autolinking statements and is idempotent', () => {
  for (const call of ['config = use_native_modules!', 'config = use_native_modules!(config_command)']) {
    const original = `target 'Jainune' do\n  ${call}\nend\n`;
    const output = addSecurityPod(original);
    assert.ok(output.includes(`  ${call}\n`));
    assert.equal(output.match(/pod 'JainuneSecurityModule'/g).length, 1);
    assert.equal(addSecurityPod(output), output);
  }
  assert.throws(() => addSecurityPod('# no app target'), /Cannot locate/);
});

test('default Play billing fails before creating or charging a Razorpay order', async () => {
  let calls = 0;
  const billing = loadTs('src/services/billingService.ts', {
    'react-native': { Platform: { OS: 'android' } },
    'react-native-razorpay': { open: async () => { calls++; } },
    'expo-secure-store': {},
    '../api/profileApi': { createSubscriptionOrder: async () => { calls++; }, createArcadeOrder: async () => { calls++; } },
    '../security/inputValidation': {}, '../theme/tokens': { colors: {} },
  });
  await assert.rejects(billing.purchaseSubscription({ plan_id: 'monthly' }), /PLAY_BILLING_MODULE_UNAVAILABLE/);
  await assert.rejects(billing.purchaseArcadeRolls('spin', 'Spin'), /PLAY_BILLING_MODULE_UNAVAILABLE/);
  assert.equal(calls, 0);
});

test('iOS never falls back to Razorpay when StoreKit is absent', async () => {
  let calls = 0;
  const billing = loadTs('src/services/billingService.ts', {
    'react-native': { Platform: { OS: 'ios' } },
    'react-native-razorpay': { open: async () => { calls++; } },
    'expo-secure-store': {}, '../api/profileApi': {},
    '../security/inputValidation': {}, '../theme/tokens': { colors: {} },
  }, { EXPO_PUBLIC_BILLING_PROVIDER: 'razorpay' });
  await assert.rejects(billing.purchaseSubscription({ plan_id: 'monthly' }), /STOREKIT_MODULE_UNAVAILABLE/);
  assert.equal(calls, 0);
});

test('Android creates notification channel before permission and supplies Expo project ID', async () => {
  const calls = [];
  const notifications = loadTs('src/services/notifications.ts', {
    'react-native': { Platform: { OS: 'android' } },
    'expo-constants': { expoConfig: { extra: { eas: { projectId: 'project-uuid' } } } },
    'expo-secure-store': { getItemAsync: async () => 'device-1' },
    '../api/client': { apiPost: async () => {} },
    'expo-notifications': {
      setNotificationHandler: () => {}, AndroidImportance: { HIGH: 4 },
      setNotificationChannelAsync: async () => { calls.push('channel'); },
      getPermissionsAsync: async () => ({ status: 'undetermined' }),
      requestPermissionsAsync: async () => { calls.push('permission'); return { status: 'granted' }; },
      getExpoPushTokenAsync: async ({ projectId }) => { assert.equal(projectId, 'project-uuid'); return { data: 'ExpoPushToken[test]' }; },
    },
  });
  assert.equal(await notifications.registerForPushNotificationsAsync(), 'ExpoPushToken[test]');
  assert.deepEqual(calls, ['channel', 'permission']);
});

test('raw APNs tokens are not registered with the FCM backend', async () => {
  let rawTokenCalls = 0;
  let registrations = 0;
  const notifications = loadTs('src/services/notifications.ts', {
    'react-native': { Platform: { OS: 'ios' } }, 'expo-constants': {}, 'expo-secure-store': {},
    '../api/client': { apiPost: async () => { registrations++; } },
    'expo-notifications': {
      setNotificationHandler: () => {},
      getPermissionsAsync: async () => ({ status: 'granted' }),
      getExpoPushTokenAsync: async () => { throw new Error('unconfigured'); },
      getDevicePushTokenAsync: async () => { rawTokenCalls++; return { data: 'raw-apns' }; },
    },
  });
  assert.equal(await notifications.registerForPushNotificationsAsync(), null);
  assert.equal(rawTokenCalls, 0);
  assert.equal(registrations, 0);
});
