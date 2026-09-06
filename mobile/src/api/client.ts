/**
 * Jainune API Client
 * - RS256 JWT Bearer auth via expo-secure-store (never AsyncStorage)
 * - 10s timeout, 3 retries with exponential backoff
 * - Graceful multi-server fallback
 * - Zero technical errors exposed to user
 * - Auto token refresh on 401
 * - Session-expired callback for auto-logout integration
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from "axios";
import * as SecureStore from "expo-secure-store";
import { ErrorCode, getFriendlyError } from "../utils/errors";

// ── Constants ─────────────────────────────────────────────────────────────────

const PRIMARY_BASE_URL = "https://api.jainune.com/v1";
const SERVER_URLS = [PRIMARY_BASE_URL];

export const SECURE_KEYS = {
  ACCESS_TOKEN: "jainune_access_token",
  REFRESH_TOKEN: "jainune_refresh_token",
  USER_ID: "jainune_user_id",
} as const;

// ── Session expired callback ───────────────────────────────────────────────────
// Avoids circular import: App.tsx sets this; client fires it on refresh failure.

type SessionExpiredFn = () => void;
let _onSessionExpired: SessionExpiredFn | null = null;

export function setSessionExpiredCallback(fn: SessionExpiredFn): void {
  _onSessionExpired = fn;
}

// ── Token storage (expo-secure-store only) ────────────────────────────────────

export async function saveTokens(
  accessToken: string,
  refreshToken: string,
  userId: string
): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(SECURE_KEYS.ACCESS_TOKEN, accessToken),
    SecureStore.setItemAsync(SECURE_KEYS.REFRESH_TOKEN, refreshToken),
    SecureStore.setItemAsync(SECURE_KEYS.USER_ID, userId),
  ]);
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(SECURE_KEYS.ACCESS_TOKEN),
    SecureStore.deleteItemAsync(SECURE_KEYS.REFRESH_TOKEN),
    SecureStore.deleteItemAsync(SECURE_KEYS.USER_ID),
  ]);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(SECURE_KEYS.ACCESS_TOKEN);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(SECURE_KEYS.REFRESH_TOKEN);
}

// ── Axios instance factory ────────────────────────────────────────────────────

function createClient(baseURL: string): AxiosInstance {
  return axios.create({
    baseURL,
    timeout: 10_000,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      Accept: "application/json",
    },
  });
}

let _client = createClient(SERVER_URLS[0]);
let _isRefreshing = false;
let _refreshQueue: Array<(token: string | null) => void> = [];

// Attach Bearer token to every request
_client.interceptors.request.use(async (config) => {
  const token = await getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auto-refresh on 401
_client.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (_isRefreshing) {
        return new Promise((resolve, reject) => {
          _refreshQueue.push((newToken) => {
            if (newToken) {
              originalRequest.headers = {
                ...originalRequest.headers,
                Authorization: `Bearer ${newToken}`,
              };
              resolve(_client(originalRequest));
            } else {
              reject(error);
            }
          });
        });
      }

      _isRefreshing = true;
      try {
        const refreshToken = await getRefreshToken();
        if (!refreshToken) throw new Error("No refresh token");

        const resp = await axios.post(
          `${SERVER_URLS[0]}/auth/token/refresh`,
          { refresh_token: refreshToken },
          { timeout: 10_000, headers: { "Content-Type": "application/json" } }
        );
        const { access_token, refresh_token: new_refresh } = resp.data.data;
        const userId =
          (await SecureStore.getItemAsync(SECURE_KEYS.USER_ID)) ?? "";

        await saveTokens(access_token, new_refresh, userId);

        _refreshQueue.forEach((cb) => cb(access_token));
        _refreshQueue = [];

        originalRequest.headers = {
          ...originalRequest.headers,
          Authorization: `Bearer ${access_token}`,
        };
        return _client(originalRequest);
      } catch {
        _refreshQueue.forEach((cb) => cb(null));
        _refreshQueue = [];
        // Purge tokens from secure storage
        await clearTokens();
        // Notify app to navigate to login
        _onSessionExpired?.();
        return Promise.reject(error);
      } finally {
        _isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ── Request wrapper with retry + fallback ─────────────────────────────────────

interface ApiResponse<T = unknown> {
  success: boolean;
  data: T;
  error: { code: string; message: string; details: unknown[] } | null;
  meta: { timestamp: string; request_id: string };
}

async function withRetry<T>(fn: () => Promise<T>, maxAttempts = 3): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      if (attempt > 0) {
        await new Promise((res) =>
          setTimeout(res, 500 * Math.pow(2, attempt - 1))
        );
      }
      return await fn();
    } catch (err) {
      lastError = err;
      if ((err as Record<string, unknown>)?._sessionExpired) throw err;
      if (axios.isAxiosError(err) && err.response && err.response.status < 500)
        throw err;
    }
  }
  throw lastError;
}

function normalizeResponse<T>(data: any): ApiResponse<T> {
  if (data && typeof data === "object" && "success" in data) {
    return data as ApiResponse<T>;
  }
  return {
    success: true,
    data: data as T,
    error: null,
    meta: { timestamp: new Date().toISOString(), request_id: "" },
  };
}

export async function apiPost<T = unknown>(
  path: string,
  body?: unknown
): Promise<ApiResponse<T>> {
  return withRetry(async () => {
    const resp = await _client.post<ApiResponse<T>>(path, body);
    return normalizeResponse<T>(resp.data);
  });
}

export async function apiGet<T = unknown>(
  path: string,
  params?: Record<string, unknown>
): Promise<ApiResponse<T>> {
  return withRetry(async () => {
    const resp = await _client.get<ApiResponse<T>>(path, { params });
    return normalizeResponse<T>(resp.data);
  });
}

export async function apiPut<T = unknown>(
  path: string,
  body?: unknown
): Promise<ApiResponse<T>> {
  return withRetry(async () => {
    const resp = await _client.put<ApiResponse<T>>(path, body);
    return normalizeResponse<T>(resp.data);
  });
}

export async function apiPatch<T = unknown>(
  path: string,
  body?: unknown
): Promise<ApiResponse<T>> {
  return withRetry(async () => {
    const resp = await _client.patch<ApiResponse<T>>(path, body);
    return normalizeResponse<T>(resp.data);
  });
}

export async function apiDelete<T = unknown>(
  path: string,
  params?: Record<string, unknown>
): Promise<ApiResponse<T>> {
  return withRetry(async () => {
    const resp = await _client.delete<ApiResponse<T>>(path, { params });
    return normalizeResponse<T>(resp.data);
  });
}

/**
 * Upload a file directly to a presigned S3 URL (bypasses axios client — no auth header).
 * Content-Type must exactly match what the presign URL was generated for.
 */
export async function uploadToPresignedUrl(
  presignedUrl: string,
  fileUri: string,
  contentType: string
): Promise<void> {
  const response = await fetch(fileUri);
  const blob = await response.blob();

  const uploadResponse = await fetch(presignedUrl, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: blob,
  });

  if (!uploadResponse.ok) {
    throw new Error(`S3 upload failed: ${uploadResponse.status}`);
  }
}

/**
 * Extract friendly error from API response or network error.
 * Never exposes HTTP codes to the user.
 */
export function extractError(err: unknown): { title: string; message: string } {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as ApiResponse | undefined;
    const errorCode = data?.error?.code as ErrorCode | undefined;
    if (errorCode) return getFriendlyError(errorCode);
    if (!err.response) return getFriendlyError("CONNECTION_PROBLEM");
  }
  if ((err as Record<string, unknown>)?._sessionExpired) {
    return getFriendlyError("SESSION_EXPIRED");
  }
  return getFriendlyError("TEMPORARY_ERROR");
}
