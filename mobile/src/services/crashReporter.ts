import { Platform } from "react-native";

export function initializeCrashReporting(): void {
  if (Platform.OS === "android") {
    // 1. Android: Firebase Crashlytics (Unlimited Free Spark Quota)
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const crashlytics = require("@react-native-firebase/crashlytics").default;
      crashlytics().setCrashlyticsCollectionEnabled(true);
    } catch {
      // Safe fallback if module not installed or running in Expo Go / web
    }
  } else {
    // 2. iOS & Web PWA: Sentry
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const Sentry = require("@sentry/react-native");
      if (process.env.EXPO_PUBLIC_SENTRY_DSN) {
        Sentry.init({
          dsn: process.env.EXPO_PUBLIC_SENTRY_DSN,
          enableAutoSessionTracking: true,
          tracesSampleRate: 0.1,
          beforeSend(event: any) {
            if (event.request?.headers) {
              delete event.request.headers["Authorization"];
            }
            return event;
          },
        });
      }
    } catch {
      // Safe fallback
    }
  }
}

export function recordHandledError(error: Error, context?: Record<string, any>): void {
  if (Platform.OS === "android") {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const crashlytics = require("@react-native-firebase/crashlytics").default;
      crashlytics().recordError(error);
    } catch {
      if (__DEV__) {
        console.error("[CrashReporter:Android]", error, context);
      }
    }
  } else {
    try {
      // eslint-disable-next-line @typescript-eslint/no-var-requires
      const Sentry = require("@sentry/react-native");
      Sentry.captureException(error, { extra: context });
    } catch {
      if (__DEV__) {
        console.error("[CrashReporter:Sentry]", error, context);
      }
    }
  }
}
