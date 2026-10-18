/** Re-mounts on every navigation, giving each screen one soft entrance. */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="route-enter">{children}</div>;
}
