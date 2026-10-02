import Link from "next/link";
import clsx from "clsx";
import type { KnowledgeState } from "@/lib/content";
import { Icon, type IconName } from "./Icons";

export function Breadcrumb({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-faint">
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="flex items-center gap-3">
          {i > 0 && <Icon name="chevronRight" size={12} className="text-ink-faint/70" />}
          {item.href ? (
            <Link href={item.href} className="text-accent-deep hover:underline">
              {item.label}
            </Link>
          ) : (
            <span className="text-ink-soft">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  intro,
  aside,
  className,
  tone = "light",
}: {
  eyebrow?: string;
  title: React.ReactNode;
  intro?: React.ReactNode;
  aside?: React.ReactNode;
  className?: string;
  tone?: "light" | "dark";
}) {
  return (
    <div className={clsx("mb-8 flex flex-wrap items-end justify-between gap-x-8 gap-y-4", className)}>
      <div className="max-w-[720px]">
        {eyebrow && <p className={clsx("eyebrow", tone === "dark" && "!text-[#9fc9d6]")}>{eyebrow}</p>}
        <h2
          className={clsx(
            "mt-2.5 text-[27px] font-bold leading-[1.22] tracking-[-0.025em] sm:text-[31px]",
            tone === "dark" ? "text-white" : "text-ink",
          )}
        >
          {title}
        </h2>
        {intro && (
          <p className={clsx("mt-3 text-[16.5px] leading-[1.7]", tone === "dark" ? "text-white/80" : "text-ink-soft")}>{intro}</p>
        )}
      </div>
      {aside}
    </div>
  );
}

export type ChipTone = "fresh" | "due" | "old" | "open" | "info";

const CHIP: Record<ChipTone, string> = {
  fresh: "bg-ok-soft text-ok",
  due: "bg-marigold-soft text-marigold-deep",
  old: "bg-old-soft text-old",
  open: "bg-old-soft text-old",
  info: "bg-info-soft text-info",
};

export function StatusChip({ tone, children, icon = "clock" }: { tone: ChipTone; children: React.ReactNode; icon?: IconName }) {
  return (
    <span className={clsx("inline-flex shrink-0 items-center gap-1.5 rounded-[4px] px-[7px] py-[3px] text-[12.5px] font-bold leading-[18px]", CHIP[tone])}>
      <Icon name={icon} size={13} strokeWidth={2} />
      {children}
    </span>
  );
}

/** One freshness vocabulary for every live item on the site. */
export function checkChip(state: KnowledgeState | "superseded"): { tone: ChipTone; label: string } {
  switch (state) {
    case "fresh":
      return { tone: "fresh", label: "Recently checked" };
    case "aging":
      return { tone: "due", label: "Due for a check" };
    case "stale":
      return { tone: "old", label: "Not recently checked" };
    case "missing":
      return { tone: "old", label: "Not checked yet" };
    case "superseded":
      return { tone: "old", label: "Older report" };
  }
}

export function TextLink({
  href,
  children,
  icon = "arrowRight",
  className,
  external = false,
}: {
  href: string;
  children: React.ReactNode;
  icon?: IconName | null;
  className?: string;
  external?: boolean;
}) {
  const body = (
    <>
      <span className="group-hover:underline">{children}</span>
      {icon && <Icon name={icon} size={15} strokeWidth={2} className="shrink-0 transition-transform group-hover:translate-x-0.5" />}
    </>
  );
  const cls = clsx("group inline-flex items-center gap-2 text-[14.5px] font-bold text-accent-deep", className);
  return external ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>
      {body}
    </a>
  ) : (
    <Link href={href} className={cls}>
      {body}
    </Link>
  );
}

export function Note({ children, icon = "info", className }: { children: React.ReactNode; icon?: IconName; className?: string }) {
  return (
    <div className={clsx("flex gap-3 rounded-[5px] bg-paper-muted px-5 py-4 text-[13.5px] leading-[1.75] text-ink-meta", className)}>
      <Icon name={icon} size={16} className="mt-[3px] shrink-0 text-ink-faint" />
      <div>{children}</div>
    </div>
  );
}

const AVATAR_TONES = ["bg-[#e3eef2]", "bg-[#f1e9df]", "bg-[#e9e7f2]", "bg-[#e3f0e8]", "bg-[#f2e6e6]"];

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");
}

function hashOf(text: string): number {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
}

export function Avatar({ name, size = 32, ring = false }: { name: string; size?: number; ring?: boolean }) {
  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.34 }}
      className={clsx(
        "flex shrink-0 items-center justify-center rounded-full font-bold text-ink",
        AVATAR_TONES[hashOf(name) % AVATAR_TONES.length],
        ring && "ring-2 ring-white",
      )}
    >
      {initials(name)}
    </span>
  );
}

export function AvatarStack({ names, size = 34 }: { names: string[]; size?: number }) {
  return (
    <div className="flex -space-x-2">
      {names.map((n) => (
        <Avatar key={n} name={n} size={size} ring />
      ))}
    </div>
  );
}

type ButtonVariant = "cta" | "primary" | "outline" | "light";

const BUTTON: Record<ButtonVariant, string> = {
  cta: "bg-cta text-cta-ink hover:bg-cta-deep",
  primary: "bg-accent-deep text-white hover:bg-accent",
  outline: "border border-border-strong bg-white text-ink hover:border-ink-soft",
  light: "bg-white text-ink hover:bg-paper-muted",
};

export function ButtonLink({
  href,
  children,
  variant = "cta",
  icon = "arrowUpRight",
  className,
}: {
  href: string;
  children: React.ReactNode;
  variant?: ButtonVariant;
  icon?: IconName | null;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={clsx(
        "inline-flex min-h-[44px] items-center justify-center gap-2.5 rounded-[5px] px-[18px] text-[15px] font-bold transition",
        BUTTON[variant],
        className,
      )}
    >
      {children}
      {icon && <Icon name={icon} size={16} strokeWidth={2} />}
    </Link>
  );
}

/** Small uppercase label used inside cards ("STAYS & SERVICES"). */
export function CardEyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={clsx("text-[11.5px] font-semibold uppercase tracking-[0.12em] text-ink-meta", className)}>{children}</p>;
}
