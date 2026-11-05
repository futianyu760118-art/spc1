export function scalePx(px: number): string {
  return `calc(${px}px * var(--font-size-scale, 1))`
}
