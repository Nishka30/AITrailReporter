import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { content } from "@/lib/content";
import { VoicePlayer } from "@/components/VoicePlayer";
import { formatValueEntries, timeAgoLabel } from "@/lib/content/freshness";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ observationId: string }>;
}): Promise<Metadata> {
  const { observationId } = await params;
  const observation = await content.getObservation(observationId);
  if (!observation) return {};
  return {
    title: observation.evidence ? observation.evidence.slice(0, 60) : observation.display_name,
    description: observation.evidence ?? undefined,
  };
}

export default async function ObservationPage({
  params,
}: {
  params: Promise<{ observationId: string }>;
}) {
  const { observationId } = await params;
  const observation = await content.getObservation(observationId);
  if (!observation) notFound();

  const details = formatValueEntries(observation.value);

  return (
    <div>
      {observation.has_photo && observation.photo_url && (
        <section className="relative flex min-h-[60vh] items-end overflow-hidden bg-ink">
          <Image src={observation.photo_url} alt="" fill priority sizes="100vw" className="object-cover opacity-90" />
          <div className="absolute inset-0 bg-gradient-to-t from-ink via-ink/20 to-transparent" />
        </section>
      )}

      <div className="mx-auto max-w-2xl px-5 py-14 sm:px-8">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-marigold-deep">{observation.display_name}</p>

        {observation.has_audio ? (
          <>
            <h1 className="mt-3 font-heading text-3xl font-extrabold text-ink sm:text-4xl">A story from the trail</h1>
            <div className="mt-8">
              <VoicePlayer audioUrl={observation.audio_url} transcript={observation.transcript} guideName={observation.guide_name} />
            </div>
            {observation.evidence && <p className="mt-6 text-[15px] leading-relaxed text-ink-soft">{observation.evidence}</p>}
          </>
        ) : (
          <h1 className="mt-3 font-heading text-2xl font-bold leading-snug text-ink sm:text-3xl">
            &ldquo;{observation.evidence}&rdquo;
          </h1>
        )}

        {details.length > 0 && (
          <dl className="mt-8 grid grid-cols-2 gap-4 rounded-2xl border border-border bg-paper-elevated p-5 sm:grid-cols-3">
            {details.map((d) => (
              <div key={d.label}>
                <dt className="text-xs font-semibold uppercase tracking-wide text-ink-faint">{d.label}</dt>
                <dd className="mt-1 text-sm font-medium text-ink">{d.text}</dd>
              </div>
            ))}
          </dl>
        )}

        <p className="mt-8 text-sm text-ink-faint">
          Reported by {observation.guide_name}, local guide · {timeAgoLabel(observation.observed_at)}
        </p>

        {observation.nearest_place_id && (
          <Link
            href={`/places/${observation.nearest_place_id}`}
            className="mt-10 flex items-center justify-between rounded-2xl border border-border bg-paper-muted/60 px-5 py-4 text-sm font-semibold text-ink transition hover:border-marigold-deep hover:text-marigold-deep"
          >
            See what else travellers noticed near {observation.nearest_place_name} →
          </Link>
        )}
      </div>
    </div>
  );
}
