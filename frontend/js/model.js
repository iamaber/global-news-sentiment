import { mean } from "./dom.js";

export function indexRegistry(registry) {
  const regionByKey = new Map(registry.regions.map((region) => [region.key, region]));
  const countryByIso = new Map();
  for (const region of registry.regions) {
    for (const country of region.countries) countryByIso.set(country.iso3, { ...country, region });
  }
  const feedCountry = new Map(registry.regions.flatMap((r) => r.feeds.map((f) => [f.name, f.country])));
  return {
    ...registry,
    regionByKey,
    countryByIso,
    feedCountry,
    topicByKey: new Map(registry.topics.map((topic) => [topic.key, topic])),
    countriesByName: [...countryByIso.values()].sort((a, b) => a.name.localeCompare(b.name, "en")),
    outletCount: feedCountry.size,
  };
}

export function indexSnapshot(snapshot) {
  const headlineById = new Map(snapshot.headlines.map((headline) => [headline.id, headline]));
  const regionByKey = new Map(snapshot.regions.map((region) => [region.key, region]));
  const scored = snapshot.regions.filter((region) => region.headlines > 0);
  return {
    ...snapshot,
    headlineById,
    regionByKey,
    mapBound: Math.max(20, ...scored.map((region) => Math.abs(region.index))),
    globalIndex: mean(snapshot.headlines.map((headline) => headline.index)),
  };
}

export const byIndexDesc = (a, b) => b.index - a.index;
