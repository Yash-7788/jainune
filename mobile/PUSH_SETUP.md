# Android push setup

The checked-in `android/` project uses Firebase Cloud Messaging through
`expo-notifications`. A production EAS build requires two Firebase artifacts
for the **same Firebase project and Android package `com.jainune.app`**:

1. Add the Android app in Firebase Spark and download `google-services.json`.
   In EAS, create a **file** environment variable named
   `GOOGLE_SERVICES_JSON` containing that file. The build hook copies it to
   `android/app/google-services.json` before Gradle runs. The file is ignored
   by Git. A production EAS build fails early if it is absent or has the
   wrong package name.
2. Upload the Firebase FCM V1 service-account credential to the Android app's
   **EAS push credentials**. This is separate from the `GOOGLE_SERVICES_JSON`
   file variable. The backend can also use a service-account JSON as Render
   `FCM_SERVICE_ACCOUNT_JSON` when sending to raw device tokens; keep its
   `FCM_PROJECT_ID` consistent with the same Firebase project.

The mobile app currently registers an Expo push token first. The backend
routes Expo tokens through Expo Push and raw device tokens through FCM. A
valid EAS credential is still needed for Expo to deliver Android pushes.

After a credentialed build, install it on a device, grant notification
permission, register the token, and send a push through the actual backend.
Local TypeScript checks and a build without Firebase credentials cannot
confirm delivery.

References: [Expo FCM V1 credentials](https://docs.expo.dev/push-notifications/fcm-credentials/),
[Firebase Android configuration](https://firebase.google.com/docs/android/setup).
