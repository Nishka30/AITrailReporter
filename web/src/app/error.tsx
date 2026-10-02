"use client";

export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#fff", color: "#25384a" }}>
        <div style={{ maxWidth: 640, margin: "0 auto", padding: "120px 24px" }}>
          <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "#596875" }}>Something went wrong</p>
          <h1 style={{ fontSize: 34, margin: "12px 0 0", letterSpacing: "-0.03em" }}>We couldn&rsquo;t load this page.</h1>
          <p style={{ fontSize: 17, lineHeight: 1.7, color: "#596875" }}>We couldn&rsquo;t reach our reports just now. Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => retry()}
            style={{ marginTop: 16, minHeight: 44, padding: "0 20px", border: 0, borderRadius: 5, background: "#0a789b", color: "#fff", fontSize: 15, fontWeight: 700, cursor: "pointer" }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
