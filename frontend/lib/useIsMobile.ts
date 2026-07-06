"use client";

import { useEffect, useState } from "react";

/** true below `maxWidth`px, false at/above, null before first client render
 *  (SSR can't know the viewport — callers should render nothing until known
 *  to avoid mounting the wrong layout and flashing). */
export default function useIsMobile(maxWidth = 768): boolean | null {
  const [isMobile, setIsMobile] = useState<boolean | null>(null);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${maxWidth - 1}px)`);
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [maxWidth]);

  return isMobile;
}
