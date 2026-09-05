# ==============================================================================
# JAINUNE PROGUARD / R8 PRODUCTION SECURITY & CODE OBFUSCATION RULES
# ==============================================================================
# Prevents APK decompilation, reverses symbol names, strips logging, protects source.

# Enable aggressive class and member renaming
-repackageclasses ''
-allowaccessmodification

# Obfuscation dictionary — random flat mapping
-overloadaggressively
-useuniqueclassmembernames

# Strip all source file names and line numbers from compiled bytecode
-renamesourcefileattribute SourceFile
-keepattributes !SourceFile,!LineNumberTable

# Strip all Android Log statements in release builds (prevents information leakage)
-assumenosideeffects class android.util.Log {
    public static boolean isLoggable(java.lang.String, int);
    public static int v(...);
    public static int d(...);
    public static int i(...);
    public static int w(...);
    public static int e(...);
}

# Preserve React Native entry point and bridge
-keep class com.facebook.react.** { *; }
-keep class com.facebook.hermes.** { *; }
-keep interface com.facebook.react.bridge.** { *; }

# Protect Native Security Bridge
-keep class com.jainune.security.** { *; }
