import type { ReactNode } from "react";

export function Page({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-4xl px-4 py-8 md:px-8">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-medium tracking-tight text-fg">{title}</h1>
            {subtitle && <p className="mt-1 text-[13.5px] text-dim">{subtitle}</p>}
          </div>
          {action}
        </header>
        {children}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-dashed border-line-strong px-6 py-12 text-center text-[13.5px] text-dim">
      <div className="dot-grid pointer-events-none absolute inset-0 opacity-60" aria-hidden />
      <div className="relative">{children}</div>
    </div>
  );
}

export const inputCls =
  "w-full rounded-lg border border-line-strong bg-ink px-3 py-2 text-[13.5px] text-fg placeholder:text-faint focus:border-white/40 focus:outline-none";
