const DARK_TEXT = "#16303C";
const LIGHT_TEXT = "#F5F8F9";
const REGION_DASHES = ["", "9 4", "2 3", "9 3 2 3"];

export function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function sentimentScale(bound) {
  const ramp = d3.piecewise(d3.interpolateLab, [token("--gloom"), token("--neutral-fill"), token("--glow")]);
  return d3.scaleDiverging([-bound, 0, bound], ramp).clamp(true);
}

export const textOn = (color) => (d3.lab(color).l > 58 ? DARK_TEXT : LIGHT_TEXT);

export function regionStyle(registry, key) {
  const position = registry.regions.findIndex((region) => region.key === key);
  return { color: token(`--region-${position + 1}`), dash: REGION_DASHES[position] ?? "" };
}
