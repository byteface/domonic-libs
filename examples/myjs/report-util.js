export const pct = (delta, base) =>
  base ? (delta / base * 100).toFixed(1).replace(/\.0$/, "") + "%" : "—";

export const trend = (delta) => (delta > 0 ? "▲" : delta < 0 ? "▼" : "—");
