"use client";

import { useEffect, useState } from "react";

// One breakpoint for the whole app; matching the DESKTOP side (min-width)
// avoids the fractional-width dead zone a max-width:767px query leaves at
// e.g. 767.5 CSS px (browser zoom / DPR scaling).
const DESKTOP_QUERY = "(min-width: 768px)";

/** true below 768px, false at/above, null before first client render
 *  (SSR can't know the viewport — callers should render nothing until known
 *  to avoid mounting the wrong layout and flashing). */
export default function useIsMobile(): boolean | null {
  const [isMobile, setIsMobile] = useState<boolean | null>(null);

  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_QUERY);
    const update = () => setIsMobile(!mq.matches);
    update();
    // addEventListener on MediaQueryList is Safari 14+; fall back for iOS ≤13.
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", update);
      return () => mq.removeEventListener("change", update);
    }
    mq.addListener(update);
    return () => mq.removeListener(update);
  }, []);

  return isMobile;
}
