"use client";

export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center bg-[#faf4e9] px-5 text-center">
        <p className="text-xl font-bold text-[#211a14]">Something went wrong</p>
        <p className="mt-2 max-w-sm text-sm text-[#4a4038]">
          We couldn&rsquo;t reach the backend. Please try again in a moment.
        </p>
        <button
          type="button"
          onClick={() => retry()}
          className="mt-6 rounded-full bg-[#211a14] px-6 py-3 text-sm font-semibold text-[#faf4e9]"
        >
          Try again
        </button>
      </body>
    </html>
  );
}
