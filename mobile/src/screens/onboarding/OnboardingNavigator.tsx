/**
 * Onboarding Navigator — wraps all 22 steps in a native stack
 * Step 1 already done in auth (phone verified), starts from Step 2.
 * ProgressBar visible throughout. Back navigation allowed freely.
 */

import React from "react";
import { View, StyleSheet, StatusBar } from "react-native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { colors, spacing } from "../../theme/tokens";
import { ProgressBar } from "../../components/core";
import { useOnboardingStore } from "../../store/onboardingStore";

// All step screens
import Step02Screen from "./steps/Step02BasicInfo";
import Step03Screen from "./steps/Step03Gender";
import Step04Screen from "./steps/Step04ShowMe";
import Step05Screen from "./steps/Step05LookingFor";
import Step06Screen from "./steps/Step06DietaryStrictness";
import Step07Screen from "./steps/Step07DietaryDetails";
import Step08Screen from "./steps/Step08CommunitySect";
import Step09Screen from "./steps/Step09Paryushan";
import Step10Screen from "./steps/Step10City";
import Step11Screen from "./steps/Step11Location";
import Step12Screen from "./steps/Step12Distance";
import Step13Screen from "./steps/Step13Relocation";
import Step14Screen from "./steps/Step14Height";
import Step15Screen from "./steps/Step15Career";
import Step16Screen from "./steps/Step16Education";
import Step17Screen from "./steps/Step17Bio";
import Step18Screen from "./steps/Step18Prompts";
import Step19Screen from "./steps/Step19Photos";
import Step20Screen from "./steps/Step20Voice";
import Step21Screen from "./steps/Step21Consent";
import Step22Screen from "./steps/Step22Complete";

export type OnboardingStackParams = {
  Step02: undefined;
  Step03: undefined;
  Step04: undefined;
  Step05: undefined;
  Step06: undefined;
  Step07: { dietaryStrictness: string };
  Step08: undefined;
  Step09: undefined;
  Step10: undefined;
  Step11: undefined;
  Step12: undefined;
  Step13: undefined;
  Step14: undefined;
  Step15: undefined;
  Step16: undefined;
  Step17: undefined;
  Step18: undefined;
  Step19: undefined;
  Step20: undefined;
  Step21: undefined;
  Step22: undefined;
};

const Stack = createNativeStackNavigator<OnboardingStackParams>();

function ProgressHeader() {
  const step = useOnboardingStore((s) => s.step);
  return (
    <View style={styles.progressHeader}>
      <ProgressBar current={step - 1} total={21} />
    </View>
  );
}

export default function OnboardingNavigator() {
  return (
    <View style={{ flex: 1 }}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />
      <ProgressHeader />
      <Stack.Navigator
        screenOptions={{
          headerShown: false,
          animation: "slide_from_right",
          contentStyle: { backgroundColor: colors.bg },
        }}
        initialRouteName="Step02"
      >
        <Stack.Screen name="Step02" component={Step02Screen} />
        <Stack.Screen name="Step03" component={Step03Screen} />
        <Stack.Screen name="Step04" component={Step04Screen} />
        <Stack.Screen name="Step05" component={Step05Screen} />
        <Stack.Screen name="Step06" component={Step06Screen} />
        <Stack.Screen name="Step07" component={Step07Screen} />
        <Stack.Screen name="Step08" component={Step08Screen} />
        <Stack.Screen name="Step09" component={Step09Screen} />
        <Stack.Screen name="Step10" component={Step10Screen} />
        <Stack.Screen name="Step11" component={Step11Screen} />
        <Stack.Screen name="Step12" component={Step12Screen} />
        <Stack.Screen name="Step13" component={Step13Screen} />
        <Stack.Screen name="Step14" component={Step14Screen} />
        <Stack.Screen name="Step15" component={Step15Screen} />
        <Stack.Screen name="Step16" component={Step16Screen} />
        <Stack.Screen name="Step17" component={Step17Screen} />
        <Stack.Screen name="Step18" component={Step18Screen} />
        <Stack.Screen name="Step19" component={Step19Screen} />
        <Stack.Screen name="Step20" component={Step20Screen} />
        <Stack.Screen name="Step21" component={Step21Screen} />
        <Stack.Screen name="Step22" component={Step22Screen} />
      </Stack.Navigator>
    </View>
  );
}

const styles = StyleSheet.create({
  progressHeader: {
    paddingHorizontal: spacing.base,
    paddingTop: 56,
    paddingBottom: spacing.sm,
    backgroundColor: colors.bg,
  },
});
