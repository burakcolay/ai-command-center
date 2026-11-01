import { api } from "./api";

export interface PendingAttachment {
  id: string;
  name: string;
  preview: string;
}

/** Image URL for an attachment id: an upload, or a rendered design ("design:<msg>:<n>"). */
export function attachmentUrl(id: string): string {
  const design = /^design:(\d+):(\d+)$/.exec(id);
  return design ? `/api/designs/${design[1]}/${design[2]}.png` : `/api/uploads/${id}`;
}

const ACCEPTED = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const MAX = 10 * 1024 * 1024;

export async function uploadImage(file: File): Promise<PendingAttachment> {
  if (!ACCEPTED.includes(file.type)) throw new Error("Yalnızca PNG, JPEG, WebP veya GIF eklenebilir.");
  if (file.size > MAX) throw new Error("Görsel 10 MB'tan büyük olamaz.");
  const data = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] ?? "");
    r.onerror = () => reject(new Error("Görsel okunamadı."));
    r.readAsDataURL(file);
  });
  const saved = await api.upload(file.name || "ekran.png", data);
  return { id: saved.id, name: saved.name, preview: attachmentUrl(saved.id) };
}
