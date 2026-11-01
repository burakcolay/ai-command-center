import { useEffect, useState } from "react";

// 5x7 glyphs, rows top→bottom. Only the letters the UI actually uses.
const GLYPHS: Record<string, string[]> = {
  A: ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
  C: ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
  E: ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
  I: ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
  K: ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
  M: ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
  N: ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
  O: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
  R: ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  U: ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
  Z: ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
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

/** Tiny 3x3 dot mark used as the logo. */
export function DotMark({ size = 18 }: { size?: number }) {
  const pts = [
    [0, 0, 1],
    [1, 0, 0.35],
    [2, 0, 1],
    [0, 1, 0.35],
    [1, 1, 1],
    [2, 1, 0.35],
    [0, 2, 1],
    [1, 2, 0.35],
    [2, 2, 1],
  ];
  return (
    <svg viewBox="0 0 12 12" width={size} height={size} aria-hidden>
      {pts.map(([x, y, o]) => (
        <circle key={`${x}${y}`} cx={2 + x * 4} cy={2 + y * 4} r={1.4} fill="#fff" opacity={o} />
      ))}
    </svg>
  );
}
