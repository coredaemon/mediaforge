import { useCallback, useState } from "react";

import { loadSection } from "../utils/sectionLoad";

export function useSessionData() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDataSection = useCallback(
    async <T,>(
      loader: () => Promise<T>,
      setter: (value: T) => void,
      message: string,
    ): Promise<T | null> => loadSection(loader, setter, setError, message),
    [],
  );

  return { loading, setLoading, error, setError, loadDataSection };
}
