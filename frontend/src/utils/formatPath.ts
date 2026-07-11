export function formatPath(path: string, maxLength = 40): string {
  if (path.length <= maxLength) return path;
  const normalized = path.replace(/\//g, "\\");
  const parts = normalized.split("\\").filter(Boolean);
  if (parts.length <= 2) {
    return `${path.slice(0, Math.max(1, maxLength - 1))}…`;
  }
  const first = parts[0] ?? "";
  const last = parts[parts.length - 1] ?? "";
  const shortened = `${first}\\…\\${last}`;
  if (shortened.length <= maxLength) return shortened;
  return `${first}\\…\\${last.slice(Math.max(0, last.length - Math.max(8, maxLength - first.length - 4)))}`;
}
