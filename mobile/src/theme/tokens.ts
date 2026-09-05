/**
 * Jainune Design System — Single Source of Truth
 * Spec: FRONTEND_SPEC.md Quarter 1 §1.1–1.2
 * All values derived from spec exactly. 8-pt grid enforced.
 */

export const colors = {
  // Brand primaries
  saffron: "#FF9C4A",
  saffronMid: "#FFB366",
  saffronLight: "#FFF4EA",

  // Accent pink
  pink: "#FFAAC4",
  pinkMid: "#FF8FAB",
  pinkLight: "#FFF0F5",

  // Neutral text
  dark: "#1C1C1E",
  mid: "#6C6C70",
  muted: "#9C9CA0",

  // Surfaces
  bg: "#FFFCFA",
  light: "#F7F3F0",
  white: "#FFFFFF",
  border: "#EDE8E3",

  // Status
  green: "#2E9E6B",
  greenLight: "#EBF7F2",
  blue: "#3B7DD8",
  blueLight: "#EBF2FF",
  red: "#E84040",
  redLight: "#FFF0F0",
} as const;

export const gradients = {
  primary: ["#FF9C4A", "#FFAAC4"] as [string, string],
  button: ["#FF9C4A", "#FF8FAB"] as [string, string],
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  base: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 48,
  huge: 64,
} as const;

export const radii = {
  xs: 4,
  sm: 6,
  md: 10,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;

export const typography = {
  // Font families — fallbacks to system sans if not loaded
  display: {
    fontFamily: "Outfit_800ExtraBold",
    fontSize: 32,
    lineHeight: 38,
    color: colors.dark,
  },
  h2: {
    fontFamily: "Outfit_700Bold",
    fontSize: 24,
    lineHeight: 30,
    color: colors.dark,
  },
  h3: {
    fontFamily: "Outfit_600SemiBold",
    fontSize: 17,
    lineHeight: 22,
    color: colors.dark,
  },
  body: {
    fontFamily: "Inter_400Regular",
    fontSize: 15,
    lineHeight: 21,
    color: colors.dark,
  },
  bodySmall: {
    fontFamily: "Inter_400Regular",
    fontSize: 13,
    lineHeight: 18,
    color: colors.mid,
  },
  caption: {
    fontFamily: "Inter_700Bold",
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 0.4,
    color: colors.mid,
  },
  cta: {
    fontFamily: "Outfit_700Bold",
    fontSize: 16,
    lineHeight: 20,
    color: colors.white,
  },
} as const;

export const shadows = {
  card: {
    shadowColor: colors.dark,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 3,
  },
  button: {
    shadowColor: colors.saffron,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 6,
  },
  heart: {
    shadowColor: colors.pink,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 8,
  },
} as const;

export type Colors = typeof colors;
export type Spacing = typeof spacing;
