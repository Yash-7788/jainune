/**
 * Onboarding store — tracks step state locally
 * Commits each step to backend on advance, allows back navigation without re-submitting
 */

import { create } from "zustand";

export interface OnboardingData {
  // Step 2
  firstName: string;
  dateOfBirth: string; // ISO string
  // Step 3
  gender: string;
  // Step 4
  showMe: string;
  // Step 5
  lookingFor: string;
  // Step 6
  dietaryStrictness: string;
  // Step 7
  eatsRootVeg: boolean;
  eatsOnionGarlic: boolean;
  // Step 8
  communitySect: string;
  // Step 9
  paryushanMode: boolean;
  // Step 10
  city: string;
  state: string;
  // Step 11
  latitude: number | null;
  longitude: number | null;
  isMocked: boolean;
  accuracyMeters: number | null;
  // Step 12
  maxDistanceKm: number;
  // Step 13
  openToRelocation: boolean;
  // Step 14
  heightCm: number | null;
  // Step 15
  jobTitle: string;
  company: string;
  // Step 16
  education: string;
  // Step 17
  bio: string;
  // Step 18
  prompts: Array<{ prompt_key: string; response_text: string; position: number }>;
  // Step 19
  photoIds: string[];
  // Step 20
  voiceSnapshotId: string | null;
  // Step 21
  consentCoreMatchmaking: boolean;
  consentFamilyContact: boolean;
  consentRelocation: boolean;
  consentMarketing?: boolean;
}

interface OnboardingStore {
  step: number;
  data: Partial<OnboardingData>;
  setStep: (step: number) => void;
  updateData: (patch: Partial<OnboardingData>) => void;
  reset: () => void;
}

const initialData: Partial<OnboardingData> = {
  maxDistanceKm: 30,
  openToRelocation: false,
  paryushanMode: false,
  eatsRootVeg: false,
  eatsOnionGarlic: false,
  consentCoreMatchmaking: true,
  consentFamilyContact: false,
  consentRelocation: false,
  prompts: [],
  photoIds: [],
};

export const useOnboardingStore = create<OnboardingStore>((set) => ({
  step: 2,
  data: initialData,

  setStep: (step) => set({ step }),
  updateData: (patch) => set((s) => ({ data: { ...s.data, ...patch } })),
  reset: () => set({ step: 2, data: initialData }),
}));
