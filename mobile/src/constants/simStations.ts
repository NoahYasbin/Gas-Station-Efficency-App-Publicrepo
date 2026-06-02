// Stations visible in the Lewes, DE map screenshot.
// posX / posY are fractions (0–1) of the rendered image width/height,
// used to position bubbles regardless of screen size.
// Effective costs computed with: 28 MPG, 4.5 gal current, 13.2 gal cap (8.7 gal to fill)

export interface SimStation {
  id: string;
  name: string;
  price: number;          // $/gal
  distanceMiles: number;  // estimated road distance from map center
  effectiveCost: number;  // (8.7 + dist/28) * price
  rank: number;
  posX: number;           // 0–1 fraction of image width
  posY: number;           // 0–1 fraction of image height
}

export const SIM_STATIONS: SimStation[] = [
  {
    id: 'bp',
    name: 'BP',
    price: 4.36,
    distanceMiles: 1.5,
    effectiveCost: 38.17,   // (8.7 + 0.054) * 4.36
    rank: 1,
    posX: 0.36,
    posY: 0.33,
  },
  {
    id: 'wawa-mid',
    name: 'Wawa',
    price: 4.42,
    distanceMiles: 1.2,
    effectiveCost: 38.64,   // (8.7 + 0.043) * 4.42
    rank: 2,
    posX: 0.57,
    posY: 0.54,
  },
  {
    id: 'wawa-low',
    name: 'Wawa',
    price: 4.40,
    distanceMiles: 3.5,
    effectiveCost: 38.83,   // (8.7 + 0.125) * 4.40
    rank: 3,
    posX: 0.81,
    posY: 0.83,
  },
  {
    id: 'wawa-top',
    name: 'Wawa',
    price: 4.50,
    distanceMiles: 0.8,
    effectiveCost: 39.28,   // (8.7 + 0.029) * 4.50
    rank: 4,
    posX: 0.55,
    posY: 0.39,
  },
  {
    id: 'safeway',
    name: 'Safeway',
    price: 4.48,
    distanceMiles: 2.5,
    effectiveCost: 39.38,   // (8.7 + 0.089) * 4.48
    rank: 5,
    posX: 0.74,
    posY: 0.62,
  },
  {
    id: 'royal-farms',
    name: 'Royal Farms',
    price: 4.50,
    distanceMiles: 3.0,
    effectiveCost: 39.63,   // (8.7 + 0.107) * 4.50
    rank: 6,
    posX: 0.80,
    posY: 0.72,
  },
];

// Color per rank: rank 1 = green, 2–3 = amber, 4+ = red
export function rankColor(rank: number): string {
  if (rank === 1) return '#2E7D32';
  if (rank <= 3)  return '#E65100';
  return '#B71C1C';
}

export const BEST = SIM_STATIONS.find(s => s.rank === 1)!;
