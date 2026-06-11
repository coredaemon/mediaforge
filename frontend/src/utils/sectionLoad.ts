import { ApiError } from "../api";

export async function loadSection<T>(
  fetcher: () => Promise<T>,
  setData: (data: T) => void,
  setSectionError: (message: string | null) => void,
  fallbackMessage: string,
): Promise<T | null> {
  setSectionError(null);
  try {
    const data = await fetcher();
    setData(data);
    return data;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : fallbackMessage;
    setSectionError(message);
    return null;
  }
}
