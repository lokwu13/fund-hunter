const MAX_SCROLL_WAIT_FRAMES = 120;

/** 等目标完成条件渲染且实际可见后再定位；快速连续导航以最后一次为准。 */
let navigationSequence = 0;

export function scrollToRenderedAnchor(anchor: string): void {
  const sequence = ++navigationSequence;
  let frames = 0;

  const attempt = () => {
    if (sequence !== navigationSequence) return;
    const target = document.getElementById(anchor);
    if (target && target.getClientRects().length > 0) {
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
      return;
    }
    frames += 1;
    if (frames < MAX_SCROLL_WAIT_FRAMES) window.requestAnimationFrame(attempt);
  };

  window.requestAnimationFrame(attempt);
}
