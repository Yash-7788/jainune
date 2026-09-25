import type { AlertButton } from "react-native";

function alert(title: string, message?: string, buttons?: AlertButton[]): void {
  const overlay = document.createElement("div");
  overlay.setAttribute("role", "presentation");
  Object.assign(overlay.style, {
    position: "fixed", inset: "0", zIndex: "10000", display: "flex",
    alignItems: "center", justifyContent: "center", padding: "20px",
    backgroundColor: "rgba(0,0,0,.55)",
  });

  const dialog = document.createElement("div");
  dialog.setAttribute("role", "alertdialog");
  dialog.setAttribute("aria-modal", "true");
  Object.assign(dialog.style, {
    width: "100%", maxWidth: "360px", padding: "24px", borderRadius: "16px",
    backgroundColor: "#fff", color: "#1c1c1e", boxShadow: "0 12px 40px rgba(0,0,0,.25)",
    fontFamily: "system-ui, sans-serif",
  });

  const heading = document.createElement("h2");
  heading.textContent = title;
  Object.assign(heading.style, { margin: "0 0 12px", fontSize: "20px" });
  dialog.appendChild(heading);
  if (message) {
    const body = document.createElement("p");
    body.textContent = message;
    Object.assign(body.style, { whiteSpace: "pre-wrap", margin: "0 0 20px", lineHeight: "1.5" });
    dialog.appendChild(body);
  }

  const actions = document.createElement("div");
  Object.assign(actions.style, { display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "flex-end" });
  const choices = buttons?.length ? buttons : [{ text: "OK" }];
  const dismiss = () => {
    document.removeEventListener("keydown", onKeyDown);
    overlay.remove();
  };
  const cancelChoice = choices.find((choice) => choice.style === "cancel");
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && cancelChoice) {
      event.preventDefault();
      dismiss();
      cancelChoice.onPress?.();
    }
  };
  document.addEventListener("keydown", onKeyDown);
  for (const choice of choices) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = choice.text || "OK";
    Object.assign(button.style, {
      minHeight: "42px", padding: "8px 14px", border: "1px solid #1c1c1e",
      borderRadius: "10px", backgroundColor: choice.style === "destructive" ? "#d83131" : "#fff",
      color: choice.style === "destructive" ? "#fff" : "#1c1c1e", fontWeight: "600",
      cursor: "pointer",
    });
    button.addEventListener("click", () => {
      dismiss();
      choice.onPress?.();
    });
    actions.appendChild(button);
  }
  dialog.appendChild(actions);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  (actions.querySelector("button") as HTMLButtonElement | null)?.focus();
}

export const Alert = { alert };
