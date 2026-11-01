/** The interesting part of a tool call, short: a file name, a pattern or a command. */
export function toolTarget(input: unknown): string {
  if (!input || typeof input !== "object") return "";
  const i = input as Record<string, unknown>;
  const path = (i.file_path ?? i.path) as string | undefined;
  const short = path ? path.split("/").filter(Boolean).slice(-2).join("/") : "";
  const what = (i.command ?? i.pattern ?? i.query ?? i.url ?? "") as string;
  const text = [what, short].filter(Boolean).join("  ·  ");
  return text.length > 140 ? `${text.slice(0, 140)}…` : text;
}
