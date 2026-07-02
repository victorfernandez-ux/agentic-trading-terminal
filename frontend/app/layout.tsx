import type { ReactNode } from "react";

export const metadata = {
  title: "Agentic Trading Terminal",
  description: "AI agents research; you approve every order.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // suppressHydrationWarning: browser extensions (e.g. Kapture) inject
    // attributes/classes onto <html>/<body> before React hydrates, which would
    // otherwise trip a hydration mismatch. Scoped to these elements only.
    <html lang="en" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        style={{
          margin: 0,
          background: "#0b0e14",
          color: "#d6deeb",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}
      >
        {children}
      </body>
    </html>
  );
}
