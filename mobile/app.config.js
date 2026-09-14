const { validateReleaseConfig } = require('./scripts/release-config.cjs');

module.exports = ({ config }) => {
  if (process.env.JAINUNE_BUILD_ENV === 'production') {
    const errors = validateReleaseConfig(process.env);
    if (errors.length) throw new Error(errors.join('\n'));
  }
  const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
  return {
    ...config,
    extra: {
      ...config.extra,
      ...(projectId ? { eas: { ...config.extra?.eas, projectId } } : {}),
    },
  };
};
