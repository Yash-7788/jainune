function validateReleaseConfig(env) {
  const errors = [];
  let api;
  let ws;
  for (const [key, protocol, suffix] of [
    ['EXPO_PUBLIC_API_URL', 'https:', '/v1'],
    ['EXPO_PUBLIC_WS_URL', 'wss:', '/v1/ws/chat'],
  ]) {
    try {
      const url = new URL(env[key]);
      if (url.protocol !== protocol || url.username || url.password || url.search || url.hash ||
          url.pathname.replace(/\/+$/, '') !== suffix ||
          /^(localhost|127\.|10\.|192\.168\.|\[::1\])/.test(url.hostname) ||
          /(?:example\.(?:com|org)|your[_-]|placeholder)/i.test(url.hostname)) {
        throw new Error('invalid');
      }
      if (key === 'EXPO_PUBLIC_API_URL') api = url;
      else ws = url;
    } catch {
      errors.push(`${key} must be an explicit ${protocol}// production URL ending in ${suffix}`);
    }
  }
  if (api && ws && api.host !== ws.host) errors.push('REST and WebSocket hosts must match for this release configuration');
  if (env.EXPO_PUBLIC_USE_MOCKS === 'true' || env.EXPO_PUBLIC_OFFLINE_DEV_MODE === 'true') errors.push('Development mocks cannot be enabled in a release');
  return errors;
}

if (require.main === module) {
  const errors = validateReleaseConfig(process.env);
  if (errors.length) {
    console.error(errors.join('\n'));
    process.exitCode = 1;
  } else {
    console.log('Release endpoint configuration is valid. Signing, billing and device acceptance are separate gates.');
  }
}
module.exports = { validateReleaseConfig };
