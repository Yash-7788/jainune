// Native apps use their existing integrity path; browser authentication uses Turnstile.
export async function getTurnstileToken(): Promise<string | null> {
  return null;
}
