import React, { useState, useEffect } from "react";
import { View, Text, StyleSheet, TouchableOpacity, Platform } from "react-native";
import { colors } from "../theme/tokens";

export default function InstallPromptBanner() {
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    if (Platform.OS === "web" && typeof navigator !== "undefined" && typeof window !== "undefined") {
      const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
      const isStandalone =
        (window.navigator as any).standalone === true ||
        (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
      if (isIos && !isStandalone) {
        setShowPrompt(true);
      }
    }
  }, []);

  if (!showPrompt) return null;

  return (
    <View style={styles.banner}>
      <Text style={styles.text}>
        Install Jainune on your iPhone: Tap <Text style={styles.bold}>Share</Text> and select <Text style={styles.bold}>Add to Home Screen</Text> 📲
      </Text>
      <TouchableOpacity
        onPress={() => setShowPrompt(false)}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
      >
        <Text style={styles.dismiss}>✕</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.saffronLight,
    borderColor: colors.saffron,
    borderWidth: 1.5,
    borderRadius: 12,
    padding: 12,
    margin: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    position: "absolute",
    top: 10,
    left: 10,
    right: 10,
    zIndex: 9999,
  },
  text: {
    fontSize: 13,
    color: colors.dark,
    flex: 1,
    marginRight: 8,
  },
  bold: {
    fontWeight: "700",
  },
  dismiss: {
    fontSize: 16,
    color: colors.mid,
    paddingHorizontal: 6,
  },
});
