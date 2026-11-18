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

function luminance(color) {
  const { r, g, b } = d3.rgb(color);
  const [R, G, B] = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

export const textOn = (color) => (contrast(color, DARK_TEXT) >= contrast(color, LIGHT_TEXT) ? DARK_TEXT : LIGHT_TEXT);

export function regionStyle(registry, key) {
  const position = registry.regions.findIndex((region) => region.key === key);
  return { color: token(`--region-${position + 1}`), dash: REGION_DASHES[position] ?? "" };
}
