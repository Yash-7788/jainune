/**
 * Auth store — Zustand with immer
 * Manages session state, token lifecycle, and onboarding routing.
 * Tokens live ONLY in expo-secure-store (never in Zustand state).
 */

import { create } from "zustand";
import { getAccessToken, getUserId, clearTokens } from "../api/client";
import { logout as apiLogout } from "../api/authApi";
import { getOnboardingStatus } from "../api/onboardingApi";
import { useOnboardingStore } from "./onboardingStore";

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

export const useAuthStore = create<AuthStore>((set, _get) => ({
  state: "loading",
  userId: null,
  isNewUser: false,
  onboardingCompleted: false,

  /** Called on app boot — check SecureStore for existing valid session */
  initSession: async () => {
    try {
      const [token, storedUserId] = await Promise.all([
        getAccessToken(),
        getUserId(),
      ]);
      if (!token) {
        set({ state: "unauthenticated", userId: null });
        return;
      }
      try {
        const status = await getOnboardingStatus();
        if (status.completed) {
          set({ state: "authenticated", userId: storedUserId, onboardingCompleted: true });
        } else {
          useOnboardingStore.getState().setStep(status.current_step || 2);
          set({ state: "onboarding", userId: storedUserId, onboardingCompleted: false });
        }
      } catch (err: unknown) {
        const apiErr = err as { _apiError?: { status?: number }; status?: number } | undefined;
        const s = apiErr?._apiError?.status || apiErr?.status;
        if (s === 401 || s === 403) {
          set({ state: "unauthenticated", userId: null });
        } else {
          // Offline / network fallback: trust saved session
          set({ state: "authenticated", userId: storedUserId });
        }
      }
    } catch {
      set({ state: "unauthenticated", userId: null });
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
    try {
      await apiLogout();
    } catch {
      await clearTokens();
    } finally {
      set({ state: "unauthenticated", userId: null, isNewUser: false, onboardingCompleted: false });
    }
  },
}));
