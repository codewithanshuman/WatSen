const paths = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  camera: <><path d="M8 5l1.5-2h5L16 5h3a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z"/><circle cx="12" cy="13" r="4"/></>,
  health: <><path d="M20.8 4.6a5.5 5.5 0 00-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 00-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 000-7.8z"/><path d="M5 12h4l2-4 2 8 2-4h4"/></>,
  layers: <><path d="M12 3L2 8l10 5 10-5-10-5zM2 12l10 5 10-5M2 16l10 5 10-5"/></>,
  search: <><circle cx="10.5" cy="10.5" r="7"/><path d="M16 16l5 5"/></>,
  arrow: <path d="M4 12h16m-6-6l6 6-6 6"/>,
  diagonal: <path d="M6 18L18 6M6 6h12v12"/>,
  chevron: <path d="M6 9l6 6 6-6"/>,
  wave: <><path d="M2 7c3-4 5 4 8 0s5 4 8 0 4 0 4 0M2 12c3-4 5 4 8 0s5 4 8 0 4 0 4 0M2 17c3-4 5 4 8 0s5 4 8 0 4 0 4 0"/></>,
  trend: <><path d="M3 17l6-6 4 4 8-11M15 4h6v6"/></>,
  people: <><circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0112 0v3M16 4a3 3 0 010 6M18 14a5 5 0 013 4v3"/></>,
  alert: <><path d="M10.2 4a2 2 0 013.6 0l8 14a2 2 0 01-1.8 3H4a2 2 0 01-1.8-3zM12 9v4M12 17h.01"/></>,
  check: <path d="M5 12l4 4L19 6"/>,
  refresh: <><path d="M20 7a8 8 0 10.5 9M20 3v5h-5"/></>,
  pin: <><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0116 0z"/><circle cx="12" cy="10" r="2.5"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  spark: <><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/></>,
  close: <path d="M6 6l12 12M18 6L6 18"/>,
  home: <><path d="M3 10l9-7 9 7v10a1 1 0 01-1 1h-5v-8H9v8H4a1 1 0 01-1-1z"/></>,
}
export default function Icon({ name = 'wave', size = 20, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.wave}</svg>
}
