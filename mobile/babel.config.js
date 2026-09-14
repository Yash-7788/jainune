module.exports = function (api) {
  api.cache(true);
  return {
    presets: ["babel-preset-expo"],
    plugins: [
      [
        "module-resolver",
        {
          root: ["."],
          alias: {
            "@": "./src",
            "@theme": "./src/theme",
            "@api": "./src/api",
            "@components": "./src/components",
            "@screens": "./src/screens",
            "@hooks": "./src/hooks",
            "@navigation": "./src/navigation",
            "@security": "./src/security",
            "@store": "./src/store",
            "@utils": "./src/utils",
          },
        },
      ],
      "react-native-worklets/plugin",
      "react-native-reanimated/plugin",
    ],
  };
};

