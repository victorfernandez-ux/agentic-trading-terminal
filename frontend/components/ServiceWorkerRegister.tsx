"use client";

import { useEffect } from "react";

/** Registers the PWA service worker. Production only — a stale cache during
 *  development is worse than no cache. Renders nothing. */
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* PWA install is progressive enhancement — the app works without it */
    });
  }, []);
  return null;
}
