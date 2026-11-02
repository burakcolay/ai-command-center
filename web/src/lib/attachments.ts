import { api } from "./api";

export type AttachmentKind = "image" | "text" | "design";

export interface PendingAttachment {
  id: string;
  name: string;
  kind: AttachmentKind;
  preview: string;
}

/** URL of an attachment id: an upload, or a rendered design ("design:<msg>:<n>"). */
export function attachmentUrl(id: string): string {
  const design = /^design:(\d+):(\d+)$/.exec(id);
  return design ? `/api/designs/${design[1]}/${design[2]}.png` : `/api/uploads/${id}`;
}

const IMAGES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const TEXT = /\.(md|markdown|txt)$/i;
const MAX_IMAGE = 10 * 1024 * 1024;
const MAX_TEXT = 1024 * 1024;

export const ACCEPT = "image/png,image/jpeg,image/webp,image/gif,.md,.markdown,.txt";

export function isAttachable(file: File): boolean {
  return IMAGES.includes(file.type) || TEXT.test(file.name);
}

/** Uploads a screenshot or a text file (an idea / spec as .md or .txt). */
export async function uploadFile(file: File): Promise<PendingAttachment> {
  const text = TEXT.test(file.name) && !IMAGES.includes(file.type);
  if (!text && !IMAGES.includes(file.type)) {
    throw new Error("Yalnızca görsel (PNG, JPEG, WebP, GIF) ya da .md / .txt dosyası eklenebilir.");
  }
  if (file.size > (text ? MAX_TEXT : MAX_IMAGE)) {
    throw new Error(text ? "Metin dosyası 1 MB'tan büyük olamaz." : "Görsel 10 MB'tan büyük olamaz.");
  }
  const data = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = () => reject(new Error("Dosya okunamadı."));
    r.readAsDataURL(file);
  });
  const saved = await api.upload(file.name || (text ? "fikir.md" : "ekran.png"), data);
  return { id: saved.id, name: saved.name, kind: text ? "text" : "image", preview: attachmentUrl(saved.id) };
}
