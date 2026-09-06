/**
 * Auth store — Zustand with immer
 * Manages session state, token lifecycle, and onboarding routing.
 * Tokens live ONLY in expo-secure-store (never in Zustand state).
 */

import { create } from "zustand";
import { getAccessToken, getRefreshToken, clearTokens } from "../api/client";
import { logout as apiLogout } from "../api/authApi";

export type AuthState = "loading" | "unauthenticated" | "authenticated" | "onboarding";

interface AuthStore {
  state: AuthState;
  userId: string | null;
  isNewUser: boolean;
  onboardingCompleted: boolean;

  // Actions
  initSession: () => Promise<void>;
  setAuthenticated: (userId: string, isNewUser: boolean, onboardingCompleted: boolean) => void;
  setOnboardingCompleted: () => void;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  state: "loading",
  userId: null,
  isNewUser: false,
  onboardingCompleted: false,

  /** Called on app boot — check SecureStore for existing valid session */
  initSession: async () => {
    try {
      const token = await getAccessToken();
      if (!token) {
        set({ state: "unauthenticated" });
        return;
      }
      try {
        const { getOnboardingStatus } = await import("../api/onboardingApi");
        const { useOnboardingStore } = await import("./onboardingStore");
        const status = await getOnboardingStatus();
        if (status.completed) {
          set({ state: "authenticated", onboardingCompleted: true });
        } else {
          useOnboardingStore.getState().setStep(status.current_step || 2);
          set({ state: "onboarding", onboardingCompleted: false });
        }
      } catch (err: any) {
        const s = err?._apiError?.status || err?.status;
        if (s === 401 || s === 403) {
          set({ state: "unauthenticated" });
        } else {
          // Offline / network fallback: trust saved session
          set({ state: "authenticated" });
        }
      }
    } catch {
      set({ state: "unauthenticated" });
    }
  },

  setAuthenticated: (userId, isNewUser, onboardingCompleted) => {
    set({
      userId,
      isNewUser,
      onboardingCompleted,
      state: onboardingCompleted ? "authenticated" : "onboarding",
    });
  },

  setOnboardingCompleted: () => {
    set({ onboardingCompleted: true, state: "authenticated" });
  },

  logout: async () => {
    await apiLogout();
    set({ state: "unauthenticated", userId: null, isNewUser: false, onboardingCompleted: false });
  },
}));
