/**
 * Hairline SVG Icons — FRONTEND_SPEC.md §5.3
 * 1.5px stroke, zero external icon libraries, zero emojis.
 */

import React from "react";
import Svg, { Circle, Ellipse, Line, Path, Polyline } from "react-native-svg";
import { colors } from "../../theme/tokens";

interface IconProps {
  color?: string;
  size?: number;
}

export function OrbitIcon({ color = colors.dark, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx="12" cy="12" r="3" stroke={color} strokeWidth="1.5" />
      <Ellipse
        cx="12"
        cy="12"
        rx="9"
        ry="4"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        transform="rotate(-30 12 12)"
      />
      <Circle cx="19" cy="8" r="1.2" fill={colors.saffron} />
    </Svg>
  );
}

export function VoiceIcon({ color = colors.saffron, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Line x1="4" y1="10" x2="4" y2="14" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <Line x1="8" y1="6" x2="8" y2="18" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <Line x1="12" y1="3" x2="12" y2="21" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <Line x1="16" y1="7" x2="16" y2="17" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <Line x1="20" y1="11" x2="20" y2="13" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </Svg>
  );
}

export function MomentumIcon({ color = colors.dark, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.5" />
      <Polyline points="12 6 12 12 16 14" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function HeartIcon({ color = colors.pinkMid, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function PassIcon({ size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Line x1="18" y1="6" x2="6" y2="18" stroke={colors.mid} strokeWidth="1.5" strokeLinecap="round" />
      <Line x1="6" y1="6" x2="18" y2="18" stroke={colors.mid} strokeWidth="1.5" strokeLinecap="round" />
    </Svg>
  );
}

export function ChatIcon({ color = colors.dark, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function PersonIcon({ color = colors.dark, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx="12" cy="8" r="4" stroke={color} strokeWidth="1.5" />
      <Path
        d="M4 20c0-4 3.6-7 8-7s8 3 8 7"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </Svg>
  );
}

export function BackIcon({ color = colors.dark, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M19 12H5M12 5l-7 7 7 7"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function CheckIcon({ color = colors.green, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M20 6L9 17l-5-5"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}
