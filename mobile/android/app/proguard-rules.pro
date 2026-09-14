# Add project specific ProGuard rules here.
# By default, the flags in this file are appended to flags specified
# in /usr/local/Cellar/android-sdk/24.3.3/tools/proguard/proguard-android.txt
# You can edit the include path and order by changing the proguardFiles
# directive in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# Strip source line numbers and source file names for anti-reverse-engineering
-renamesourcefileattribute SourceFile
-keepattributes !SourceFile,!LineNumberTable

# Strip Android logging statements from release builds (prevents PII/token leak to logcat)
-assumenosideeffects class android.util.Log {
    public static boolean isLoggable(java.lang.String, int);
    public static int v(...);
    public static int d(...);
    public static int i(...);
    public static int w(...);
    public static int e(...);
}

# Preserve React Native & Hermes core reflection interfaces
-keep class com.facebook.react.** { *; }
-keep class com.facebook.hermes.** { *; }
-keep interface com.facebook.react.bridge.** { *; }

# Preserve Expo native modules autolinking reflection
-keep class expo.modules.** { *; }

# react-native-reanimated
-keep class com.swmansion.reanimated.** { *; }
-keep class com.facebook.react.turbomodule.** { *; }

# Project & third-party keep rules
-keep class com.jainune.app.** { *; }
-keepclassmembers class com.jainune.app.JainuneSecurityModule {
    @com.facebook.react.bridge.ReactMethod *;
    public *;
}
-keep class com.razorpay.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.razorpay.**
