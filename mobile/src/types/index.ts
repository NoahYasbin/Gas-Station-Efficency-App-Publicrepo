export interface Station {
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  price_per_gallon: number;
  distance_miles: number;
  drive_time_minutes: number | null;
  effective_cost: number;
  gallons_purchased: number;
  fuel_burned_in_transit: number;
  rank: number;
  savings_vs_best: number;
  reachable: boolean;
}

export interface RecommendResponse {
  best_station: Station;
  all_stations: Station[];
  note: string;
  region_avg_price: number;
  city: string;
  state: string;
  tank_is_full: boolean;
}

export interface VehicleParams {
  mpg: number;
  tank_current: number;
  tank_capacity: number;
}
