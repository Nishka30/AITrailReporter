import Link from "next/link";
import { Icon } from "@/components/guide/Icons";

export default function NotFound() {
  return (
    <div className="page flex min-h-[60vh] flex-col justify-center py-20">
      <p className="eyebrow">Off the map</p>
      <h1 className="mt-3 text-[40px] font-bold tracking-[-0.035em] text-ink sm:text-[50px]">We couldn&rsquo;t find that page.</h1>
      <p className="mt-4 max-w-xl text-[17px] leading-[1.75] text-ink-soft">
        It may have moved, or the report behind it hasn&rsquo;t been reviewed yet.
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-6">
        <Link href="/explore" className="inline-flex min-h-[44px] items-center gap-2.5 rounded-[5px] bg-accent-deep px-5 text-[15px] font-bold text-white hover:bg-accent">
          Explore places <Icon name="arrowRight" size={16} strokeWidth={2} />
        </Link>
        <Link href="/" className="text-[15px] font-bold text-accent-deep hover:underline">
          Back to the home page
        </Link>
      </div>
    </div>
  );
}
