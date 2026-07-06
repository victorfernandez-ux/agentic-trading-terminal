import type { IChartApi } from "lightweight-charts";

/** Keep a lightweight-charts instance sized to its container.
 *
 *  ResizeObserver (not window.resize) because charts inside hidden mobile
 *  tabs mount at width 0 and only get a real width when the tab is shown;
 *  on that first zero→nonzero transition the content is refit so the user
 *  never sees a chart scrolled off-screen. Returns a cleanup function.
 */
export function observeChartWidth(el: HTMLElement, chart: IChartApi): () => void {
  let lastWidth = 0;
  const onResize = () => {
    const w = el.clientWidth;
    if (w <= 0 || w === lastWidth) return;
    chart.applyOptions({ width: w });
    if (lastWidth === 0) chart.timeScale().fitContent();
    lastWidth = w;
  };
  onResize();
  const ro = new ResizeObserver(onResize);
  ro.observe(el);
  return () => ro.disconnect();
}
