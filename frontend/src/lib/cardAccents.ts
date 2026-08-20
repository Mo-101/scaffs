export interface CardAccent {
  gradient: string;
  border: string;
  iconBg: string;
  text: string;
}

const ACCENTS: CardAccent[] = [
  {
    gradient: "from-blue-500/10 via-transparent to-transparent",
    border: "border-blue-500/20 hover:border-blue-500/40",
    iconBg: "bg-blue-500/10 text-blue-500",
    text: "text-blue-500",
  },
  {
    gradient: "from-emerald-500/10 via-transparent to-transparent",
    border: "border-emerald-500/20 hover:border-emerald-500/40",
    iconBg: "bg-emerald-500/10 text-emerald-500",
    text: "text-emerald-500",
  },
  {
    gradient: "from-amber-500/10 via-transparent to-transparent",
    border: "border-amber-500/20 hover:border-amber-500/40",
    iconBg: "bg-amber-500/10 text-amber-500",
    text: "text-amber-500",
  },
  {
    gradient: "from-purple-500/10 via-transparent to-transparent",
    border: "border-purple-500/20 hover:border-purple-500/40",
    iconBg: "bg-purple-500/10 text-purple-500",
    text: "text-purple-500",
  },
];

export function cardAccent(index: number): CardAccent {
  return ACCENTS[index % ACCENTS.length];
}