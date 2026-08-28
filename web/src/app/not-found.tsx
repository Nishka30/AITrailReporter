import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center px-5 text-center">
      <p className="font-heading text-6xl font-extrabold text-marigold-deep">404</p>
      <p className="mt-4 font-heading text-xl font-bold text-ink">We couldn&rsquo;t find that page</p>
      <p className="mt-2 text-sm text-ink-soft">It may have moved, or the report behind it hasn&rsquo;t been approved yet.</p>
      <Link href="/explore" className="mt-8 rounded-full bg-ink px-6 py-3 text-sm font-semibold text-paper transition hover:bg-marigold-deep">
        Explore places
      </Link>
    </div>
  );
}
