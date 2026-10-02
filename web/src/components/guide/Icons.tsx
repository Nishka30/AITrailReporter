const PATHS = {
  pin: (
    <>
      <path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21Z" />
      <circle cx="12" cy="9.8" r="2.3" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  chat: <path d="M20.5 11.5a8 8 0 0 1-11.6 7.1L4 20l1.5-4.3A8 8 0 1 1 20.5 11.5Z" />,
  arrowRight: <path d="M5 12h14M13 6l6 6-6 6" />,
  arrowUpRight: <path d="M7 17 17 7M8 7h9v9" />,
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5M12 8h.01" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .8-1 1.5v.3M12 16.5h.01" />
    </>
  ),
  plane: <path d="m3 13 7.5-2L15 4l2 .5-2.5 7L20 13l1 2-6.5-.5L11 19H9l1.5-4.5L3 15z" />,
  cup: (
    <>
      <path d="M5 9h11v5a5 5 0 0 1-5 5h-1a5 5 0 0 1-5-5V9Z" />
      <path d="M16 10.5h1.5a2.5 2.5 0 0 1 0 5H16M8 3.5c0 1 1 1 1 2s-1 1-1 2M12 3.5c0 1 1 1 1 2s-1 1-1 2" />
    </>
  ),
  boots: (
    <>
      <path d="M8.5 3.5c-2 0-3 1.8-3 4.5 0 2 .8 3.5.8 5h4.4c0-1.6.8-3 .8-5 0-2.6-1-4.5-3-4.5Z" />
      <path d="M6.3 15.5c0 2 .8 3.5 2.2 3.5s2.2-1.5 2.2-3.5M15.5 6c2 0 3 1.8 3 4.5 0 2-.8 3.5-.8 5h-4.4c0-1.6-.8-3-.8-5 0-2.6 1-4.5 3-4.5Z" />
    </>
  ),
  bed: (
    <>
      <path d="M3 18V7M3 12h18v6M21 18v-3" />
      <path d="M7 12V9.5A1.5 1.5 0 0 1 8.5 8h3A1.5 1.5 0 0 1 13 9.5V12" />
    </>
  ),
  book: (
    <>
      <path d="M3.5 5.5c2.8-.9 5.7-.5 8.5 1.3v12.7c-2.8-1.8-5.7-2.2-8.5-1.3V5.5Z" />
      <path d="M20.5 5.5c-2.8-.9-5.7-.5-8.5 1.3v12.7c2.8-1.8 5.7-2.2 8.5-1.3V5.5Z" />
    </>
  ),
  camera: (
    <>
      <path d="M4 8h3l1.6-2h6.8L17 8h3v11H4V8Z" />
      <circle cx="12" cy="13" r="3.4" />
    </>
  ),
  compass: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" />
    </>
  ),
  mountain: <path d="m3 19 6.5-11 4 6.5 2-3L21 19H3Z" />,
  route: (
    <>
      <circle cx="6" cy="18" r="2" />
      <circle cx="18" cy="6" r="2" />
      <path d="M8 18h7.5a3 3 0 0 0 0-6h-7a3 3 0 0 1 0-6H16" />
    </>
  ),
  flag: <path d="M5 21V4M5 4h11l-2 4 2 4H5" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  chevronDown: <path d="m6 9 6 6 6-6" />,
  chevronRight: <path d="m9 6 6 6-6 6" />,
  shop: (
    <>
      <path d="M4 9.5 5.5 4h13L20 9.5M4 9.5h16M4 9.5c0 1.6 1.3 2.5 2.7 2.5S9.3 11 9.3 9.5c0 1.6 1.3 2.5 2.7 2.5s2.7-.9 2.7-2.5c0 1.6 1.3 2.5 2.6 2.5s2.7-.9 2.7-2.5" />
      <path d="M5.5 12v8h13v-8" />
    </>
  ),
  temple: (
    <>
      <path d="M12 3v3M8 9h8l-1.5-3h-5L8 9ZM6 13h12l-2-4H8l-2 4ZM7 13v7h10v-7M10.5 20v-4h3v4" />
    </>
  ),
  layers: (
    <>
      <path d="m12 4 9 5-9 5-9-5 9-5Z" />
      <path d="m3 14 9 5 9-5" />
    </>
  ),
  calendar: (
    <>
      <rect x="4" y="5" width="16" height="15" rx="1.5" />
      <path d="M4 10h16M8.5 3v4M15.5 3v4" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
  phone: <path d="M6.5 3.5h3l1.5 4-2 1.3a10 10 0 0 0 6.2 6.2l1.3-2 4 1.5v3a2 2 0 0 1-2.2 2A16 16 0 0 1 4.5 5.7a2 2 0 0 1 2-2.2Z" />,
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16, className, strokeWidth = 1.7 }: { name: IconName; size?: number; className?: string; strokeWidth?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
