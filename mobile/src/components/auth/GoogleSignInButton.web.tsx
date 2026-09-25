import React, { useEffect, useRef } from "react";
import { View } from "react-native";

type GoogleIdentity = {
  accounts: {
    id: {
      initialize: (config: Record<string, unknown>) => void;
      renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
    };
  };
};

declare global {
  interface Window { google?: GoogleIdentity }
}

let scriptPromise: Promise<void> | null = null;
function loadGoogleIdentity(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error("Google Sign-In could not load. Please try again."));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export default function GoogleSignInButton({
  onCredential,
  onError,
}: {
  onCredential: (credential: string) => void;
  onError: (message: string) => void;
}) {
  const container = useRef<HTMLElement | null>(null);
  const credentialCallback = useRef(onCredential);
  const errorCallback = useRef(onError);
  credentialCallback.current = onCredential;
  errorCallback.current = onError;

  useEffect(() => {
    let mounted = true;
    const clientId = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;
    if (!clientId || clientId.startsWith("YOUR_")) {
      errorCallback.current("Google Sign-In is not configured yet. Please use Email sign-in.");
      return;
    }
    loadGoogleIdentity()
      .then(() => {
        if (!mounted || !container.current || !window.google) return;
        window.google.accounts.id.initialize({
          client_id: clientId,
          auto_select: false,
          ux_mode: "popup",
          callback: (response: { credential?: string }) => {
            if (mounted && response.credential) credentialCallback.current(response.credential);
          },
        });
        window.google.accounts.id.renderButton(container.current, {
          type: "standard", theme: "outline", size: "large",
          shape: "pill", text: "continue_with", width: 320,
        });
      })
      .catch((error: Error) => {
        if (mounted) errorCallback.current(error.message);
      });
    return () => { mounted = false; };
  }, []);

  return <View ref={container as any} style={{ minHeight: 52, alignItems: "center", justifyContent: "center" }} />;
}
