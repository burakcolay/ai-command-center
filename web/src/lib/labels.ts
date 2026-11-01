import type { TaskStatus } from "./types";

export const STATUS_LABEL: Record<TaskStatus, string> = {
  planning: "Planlanıyor",
  waiting_approval: "Onay bekliyor",
  queued: "Kuyrukta",
  running: "Çalışıyor",
  paused: "Duraklatıldı",
  completed: "Tamamlandı",
  failed: "Başarısız",
  cancelled: "İptal edildi",
};

export const MODEL_STATE_LABEL: Record<string, string> = {
  available: "Kullanılabilir",
  limited: "Sınırlı",
  cooldown: "Bekleme süresinde",
  auth_required: "Giriş gerekli",
  membership_required: "Üyelik gerekli",
  paid_access_required: "Ücretli erişim — engellendi",
  not_configured: "Kurulu değil",
  offline: "Çevrimdışı",
  unknown: "Bilinmiyor",
};

export const BILLING_LABEL: Record<string, string> = {
  subscription: "Mevcut abonelik",
  local_free: "Yerel · ücretsiz",
  free_tier: "Ücretsiz katman",
  paid_api: "Ücretli API · kapalı",
};

export const USAGE_SOURCE_LABEL: Record<string, string> = {
  verified: "doğrulanmış",
  estimated: "tahmini",
  user: "kullanıcı girdi",
  unknown: "bilinmiyor",
};

export const WINDOW_LABEL: Record<string, string> = {
  five_hour: "5 saatlik pencere",
  seven_day: "7 günlük pencere",
};

export const AGENT_LABEL: Record<string, string> = {
  orchestrator: "Orchestrator",
  research: "Araştırma",
  architect: "Mimar",
  developer: "Geliştirici",
  qa: "QA",
  reviewer: "İnceleme",
  docs: "Dokümantasyon",
};

/** Short model names for step badges. */
export const ADAPTER_LABEL: Record<string, string> = {
  claude_code: "Claude",
  codex: "Codex",
  ollama: "Yerel",
  grok: "Grok",
  mock: "Demo",
};

