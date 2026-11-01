import { useEffect, useState } from "react";

// 5x7 glyphs, rows top→bottom. Only the letters the UI actually uses.
const GLYPHS: Record<string, string[]> = {
  B: ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
  I: ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
  O: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
  R: ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  " ": ["000", "000", "000", "000", "000", "000", "000"],
};

function columns(text: string): boolean[][] {
  const cols: boolean[][] = [];
  [...text.toUpperCase()].forEach((ch, i) => {
    const g = GLYPHS[ch] ?? GLYPHS[" "];
    if (i > 0) cols.push(Array(7).fill(false));
    for (let x = 0; x < g[0].length; x++) cols.push(g.map((row) => row[x] === "1"));
  });
  return cols;
}

/** Text drawn as a grid of dots; lit dots sweep in left→right on mount. */
export function DotMatrix({
  text,
  dot = 6,
  gap = 3,
  pad = 1,
  className = "",
}: {
  text: string;
  dot?: number;
  gap?: number;
  pad?: number;
  className?: string;
}) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setOn(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const cols = columns(text);
  const cell = dot + gap;
  const w = (cols.length + pad * 2) * cell;
  const h = (7 + pad * 2) * cell;
  const r = dot / 2;

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width={w}
      height={h}
      className={className}
      role="img"
      aria-label={text}
    >
      {Array.from({ length: cols.length + pad * 2 }, (_, x) =>
        Array.from({ length: 7 + pad * 2 }, (_, y) => {
          const lit = cols[x - pad]?.[y - pad] ?? false;
          return (
            <circle
              key={`${x}-${y}`}
              cx={x * cell + cell / 2}
              cy={y * cell + cell / 2}
              r={r}
              fill="#fff"
              style={{
                opacity: lit ? (on ? 1 : 0.06) : 0.06,
                transition: `opacity 420ms ease ${x * 22 + y * 8}ms`,
              }}
            />
          );
        }),
      )}
    </svg>
  );
}

/** Logo: a core dot, a faint ring of dots, and one bright dot in slow orbit. */
export function OrbitMark({ size = 18 }: { size?: number }) {
  const ring = Array.from({ length: 10 }, (_, i) => {
    const a = (i / 10) * Math.PI * 2;
    return [12 + Math.cos(a) * 8.5, 12 + Math.sin(a) * 8.5];
  });
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>
      <circle cx={12} cy={12} r={2.6} fill="#fff" />
      {ring.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={1.1} fill="#fff" opacity={0.28} />
      ))}
      <g className="animate-orbit" style={{ transformOrigin: "12px 12px" }}>
        <circle cx={20.5} cy={12} r={1.9} fill="#fff" />
      </g>
    </svg>
  );
}
