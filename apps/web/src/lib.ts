export function waitLabel(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

const ORDER = ["GREEN", "YELLOW", "ORANGE", "RED"];
export const priorityRank = (p: string) => ORDER.indexOf(p);
