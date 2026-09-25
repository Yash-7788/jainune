type TurnstileApi = {
  render: (element: HTMLElement, options: Record<string, unknown>) => string;
  remove: (widgetId: string) => void;
};

declare global {
  interface Window { turnstile?: TurnstileApi }
}

let scriptPromise: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = () => {
      if (window.turnstile) resolve();
      else {
        scriptPromise = null;
        reject(new Error("Security check did not load."));
      }
    };
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error("Security check could not load. Please try again."));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

/** Obtain a fresh, single-use Turnstile token for each browser auth request. */
export async function getTurnstileToken(): Promise<string> {
  const sitekey = process.env.EXPO_PUBLIC_TURNSTILE_SITE_KEY;
  if (!sitekey || sitekey.startsWith("YOUR_")) {
    throw new Error("Web security verification is not configured yet.");
  }
  await loadScript();
  return new Promise<string>((resolve, reject) => {
    const overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    Object.assign(overlay.style, {
      position: "fixed", inset: "0", zIndex: "10001", display: "flex",
      alignItems: "center", justifyContent: "center", padding: "20px",
      backgroundColor: "rgba(0,0,0,.55)",
    });
    const card = document.createElement("div");
    Object.assign(card.style, {
      backgroundColor: "white", borderRadius: "16px", padding: "24px",
      maxWidth: "360px", width: "100%", fontFamily: "system-ui, sans-serif",
    });
    const title = document.createElement("h2");
    title.textContent = "Security check";
    Object.assign(title.style, { margin: "0 0 16px", fontSize: "20px" });
    const widget = document.createElement("div");
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    Object.assign(cancel.style, { marginTop: "18px", padding: "10px 16px", cursor: "pointer" });
    card.append(title, widget, cancel);
    overlay.appendChild(card);
    document.body.appendChild(overlay);

    let settled = false;
    let widgetId: string | undefined;
    const finish = (token?: string, error?: Error) => {
      if (settled) return;
      settled = true;
      if (widgetId) window.turnstile?.remove(widgetId);
      overlay.remove();
      if (token) resolve(token);
      else reject(error || new Error("Security check was cancelled."));
    };
    cancel.onclick = () => finish();
    try {
      widgetId = window.turnstile!.render(widget, {
        sitekey, theme: "light",
        callback: (token: string) => finish(token),
        "error-callback": () => finish(undefined, new Error("Security check failed. Please try again.")),
        "expired-callback": () => finish(undefined, new Error("Security check expired. Please try again.")),
      });
      if (settled && widgetId) window.turnstile?.remove(widgetId);
    } catch {
      finish(undefined, new Error("Security check could not start."));
    }
  });
}
