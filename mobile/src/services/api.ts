import { RecommendResponse, VehicleParams } from '../types';

const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';

export interface RecommendResult {
  data: RecommendResponse;
  isMock: boolean;
  error?: string;
}

export async function fetchRecommendation(
  latitude: number,
  longitude: number,
  vehicle: VehicleParams,
  searchRadiusMiles = 5,
  fuelGrade = 'regular'
): Promise<RecommendResult> {
  try {
    const res = await fetch(`${BASE_URL}/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude,
        longitude,
        vehicle,
        search_radius_miles: searchRadiusMiles,
        fuel_grade: fuelGrade,
      }),
    });

    if (!res.ok) {
      // Parse the backend error message so we can show it
      let detail = `Server error ${res.status}`;
      try {
        const body = await res.json();
        if (body.detail) detail = body.detail;
      } catch {}
      console.error('Backend error:', detail);
      return { data: _mockData(), isMock: true, error: detail };
    }

    return { data: await res.json(), isMock: false };
  } catch (e: any) {
    const msg = e?.message ?? 'Network error — is the backend running?';
    console.error('fetchRecommendation failed:', msg);
    return { data: _mockData(), isMock: true, error: msg };
  }
}

// Minimal mock so the UI renders in demo mode — no imported constant needed
function _mockData(): RecommendResponse {
  return {
    best_station: {
      name: 'Demo Station',
      address: '',
      latitude: 0,
      longitude: 0,
      price_per_gallon: 0,
      distance_miles: 0,
      drive_time_minutes: null,
      effective_cost: 0,
      gallons_purchased: 0,
      fuel_burned_in_transit: 0,
      rank: 1,
      savings_vs_best: 0,
      reachable: true,
    },
    all_stations: [],
    note: '',
    region_avg_price: 0,
    city: '',
    state: '',
    tank_is_full: false,
  };
}
