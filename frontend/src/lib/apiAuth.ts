const KEY = "qa_api_auth_key";

export function getApiAuthKey(): string {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

export function setApiAuthKey(key: string): void {
  try {
    if (key) {
      localStorage.setItem(KEY, key);
    } else {
      localStorage.removeItem(KEY);
    }
  } catch {
    // ignore
  }
}