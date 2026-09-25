// SecureStore has no web implementation. Browser storage is scoped to the PWA
// origin; never put these values in URLs or the server-rendered HTML.
const prefix = "jainune:";

export async function getItemAsync(key: string): Promise<string | null> {
  return window.localStorage.getItem(prefix + key);
}

export async function setItemAsync(key: string, value: string): Promise<void> {
  window.localStorage.setItem(prefix + key, value);
}

export async function deleteItemAsync(key: string): Promise<void> {
  window.localStorage.removeItem(prefix + key);
}
