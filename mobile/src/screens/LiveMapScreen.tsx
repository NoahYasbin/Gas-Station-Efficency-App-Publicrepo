import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import MapView, { Callout, Marker, Region } from 'react-native-maps';
import * as Location from 'expo-location';
import { StatusBar } from 'expo-status-bar';

import { fetchRecommendation } from '../services/api';
import { RecommendResponse } from '../types';

const VEHICLE = { mpg: 28, tank_current: 4.5, tank_capacity: 13.2 };

function rankColor(rank: number): string {
  if (rank === 1) return '#2E7D32';
  if (rank <= 3) return '#E65100';
  return '#B71C1C';
}

function userRegion(lat: number, lng: number): Region {
  return { latitude: lat, longitude: lng, latitudeDelta: 0.06, longitudeDelta: 0.06 };
}

function stationRegion(lat: number, lng: number, stations: RecommendResponse['all_stations']): Region {
  const lats = [lat, ...stations.map(s => s.latitude)];
  const lngs = [lng, ...stations.map(s => s.longitude)];
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
  const pad = 0.01;
  return {
    latitude:      (minLat + maxLat) / 2,
    longitude:     (minLng + maxLng) / 2,
    latitudeDelta:  Math.max(maxLat - minLat + pad * 2, 0.04),
    longitudeDelta: Math.max(maxLng - minLng + pad * 2, 0.04),
  };
}

type Status = 'locating' | 'fetching' | 'ready' | 'error';

export default function LiveMapScreen() {
  const mapRef = useRef<MapView>(null);
  const [status, setStatus]     = useState<Status>('locating');
  const [errorMsg, setErrorMsg] = useState('');
  const [userLat, setUserLat]   = useState(0);
  const [userLng, setUserLng]   = useState(0);
  const [data, setData]         = useState<RecommendResponse | null>(null);
  const [isMock, setIsMock]     = useState(false);

  const load = async () => {
    setStatus('locating');
    setErrorMsg('');

    // 1. Location permission
    const { status: perm } = await Location.requestForegroundPermissionsAsync();
    if (perm !== 'granted') {
      setErrorMsg('Location permission denied. Enable it in Settings to find nearby stations.');
      setStatus('error');
      return;
    }

    // 2. GPS fix
    let pos: Location.LocationObject;
    try {
      pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    } catch {
      setErrorMsg('Could not read GPS position. Make sure Location Services are on.');
      setStatus('error');
      return;
    }
    const { latitude, longitude } = pos.coords;
    setUserLat(latitude);
    setUserLng(longitude);

    // Center map on real location immediately, before API responds
    setTimeout(() => mapRef.current?.animateToRegion(userRegion(latitude, longitude), 600), 100);

    // 3. Fetch stations
    setStatus('fetching');
    const { data: result, isMock: mock, error } = await fetchRecommendation(latitude, longitude, VEHICLE);
    setData(result);
    setIsMock(mock);
    if (mock && error) setErrorMsg(error);
    setStatus('ready');

    // Animate to fit stations only when they are real (near the user)
    if (!mock && result.all_stations.length > 0) {
      const region = stationRegion(latitude, longitude, result.all_stations);
      setTimeout(() => mapRef.current?.animateToRegion(region, 800), 300);
    }
  };

  useEffect(() => { load(); }, []);

  // ── Loading ──
  if (status === 'locating' || status === 'fetching') {
    return (
      <View style={styles.center}>
        <StatusBar style="dark" />
        <ActivityIndicator size="large" color="#2E7D32" />
        <Text style={styles.loadingText}>
          {status === 'locating' ? 'Getting your location…' : 'Searching GasBuddy near you…'}
        </Text>
        {status === 'fetching' && (
          <Text style={styles.loadingSubText}>First load takes 30–60 s while GasBuddy is scraped.</Text>
        )}
      </View>
    );
  }

  // ── Error ──
  if (status === 'error') {
    return (
      <View style={styles.center}>
        <StatusBar style="dark" />
        <Text style={styles.errorIcon}>⚠️</Text>
        <Text style={styles.errorText}>{errorMsg}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={load}>
          <Text style={styles.retryText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Ready ──
  const stations = data!.all_stations;
  const best     = data!.best_station;
  const maxSavings = Math.max(0, ...stations.filter(s => s.rank !== 1).map(s => s.effective_cost - best.effective_cost));

  // When using mock data, center on real user location (ignore mock SF coords)
  const initialRegion = isMock
    ? userRegion(userLat, userLng)
    : stationRegion(userLat, userLng, stations);

  return (
    <View style={styles.container}>
      <StatusBar style="dark" />

      {/* ── Header ── */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>⛽  Gas Finder</Text>
        <Text style={styles.headerSub}>
          {isMock
            ? 'Demo mode — start backend for real prices'
            : `${data!.city}${data!.city && data!.state ? ', ' : ''}${data!.state}  ·  avg $${data!.region_avg_price.toFixed(2)}/gal`}
        </Text>
      </View>

      {/* ── Demo mode banner ── */}
      {isMock && (
        <View style={styles.demoBanner}>
          <Text style={styles.demoBannerText}>
            ⚡ Backend error: {errorMsg || 'could not reach server'}
          </Text>
        </View>
      )}

      {/* ── Map ── */}
      <MapView
        ref={mapRef}
        style={styles.map}
        initialRegion={initialRegion}
        showsUserLocation
        showsMyLocationButton
      >
        {stations.map(station => {
          const color  = rankColor(station.rank);
          const isBest = station.rank === 1;

          // In mock mode the station coordinates are SF placeholder data — skip rendering
          // markers far from the user so the map stays useful
          if (isMock) return null;

          return (
            <Marker
              key={`${station.name}-${station.latitude}-${station.longitude}`}
              coordinate={{ latitude: station.latitude, longitude: station.longitude }}
              anchor={{ x: 0.5, y: 1 }}
            >
              <View style={styles.markerWrapper}>
                {isBest && (
                  <View style={[styles.bestTag, { backgroundColor: color }]}>
                    <Text style={styles.bestTagText}>BEST</Text>
                  </View>
                )}
                <View style={[styles.markerBubble, { borderColor: color, borderWidth: isBest ? 2.5 : 1.5 }]}>
                  <Text style={[styles.markerName, { color }]} numberOfLines={1}>{station.name}</Text>
                  <Text style={styles.markerPrice}>${station.price_per_gallon.toFixed(2)}</Text>
                </View>
                <View style={[styles.markerTail, { borderTopColor: color }]} />
              </View>

              <Callout tooltip={false}>
                <View style={styles.callout}>
                  <Text style={[styles.calloutRank, { color }]}>#{station.rank}  {station.name}</Text>
                  <Text style={styles.calloutLine}>
                    ${station.price_per_gallon.toFixed(2)}/gal  ·  {station.distance_miles.toFixed(1)} mi away
                  </Text>
                  <Text style={styles.calloutLine}>${station.effective_cost.toFixed(2)} total cost</Text>
                  {station.drive_time_minutes != null && (
                    <Text style={styles.calloutSub}>~{Math.round(station.drive_time_minutes)} min drive</Text>
                  )}
                  <Text style={styles.calloutAddr} numberOfLines={2}>{station.address}</Text>
                </View>
              </Callout>
            </Marker>
          );
        })}
      </MapView>

      {/* ── Bottom panel ── */}
      <View style={styles.panel}>
        <View style={styles.panelRow}>
          <View style={[styles.rankBadge, { backgroundColor: rankColor(1) }]}>
            <Text style={styles.rankText}>#1</Text>
          </View>
          <View style={styles.panelMain}>
            <Text style={styles.panelName}>{best.name}</Text>
            <Text style={styles.panelSub}>
              {best.distance_miles.toFixed(1)} mi away · ${best.price_per_gallon.toFixed(2)}/gal
            </Text>
          </View>
          <View style={styles.panelRight}>
            <Text style={styles.effectiveCost}>${best.effective_cost.toFixed(2)}</Text>
            <Text style={styles.effectiveCostLabel}>total cost</Text>
          </View>
        </View>

        {maxSavings > 0 && (
          <Text style={styles.noteText}>💡 {data!.note}</Text>
        )}

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.strip}>
          {stations.map(s => (
            <View
              key={`${s.name}-${s.rank}`}
              style={[styles.stripCard, s.rank === 1 && { borderColor: rankColor(1), borderWidth: 2 }]}
            >
              <Text style={[styles.stripRank, { color: rankColor(s.rank) }]}>#{s.rank}</Text>
              <Text style={styles.stripName} numberOfLines={1}>{s.name}</Text>
              <Text style={styles.stripPrice}>${s.price_per_gallon.toFixed(2)}</Text>
              <Text style={styles.stripEff}>${s.effective_cost.toFixed(2)} total</Text>
            </View>
          ))}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },

  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, backgroundColor: '#f5f5f5' },
  loadingText:    { marginTop: 16, fontSize: 16, color: '#333', textAlign: 'center' },
  loadingSubText: { marginTop: 8,  fontSize: 12, color: '#888', textAlign: 'center' },
  errorIcon: { fontSize: 40, marginBottom: 12 },
  errorText: { fontSize: 15, color: '#555', textAlign: 'center', marginBottom: 24, lineHeight: 22 },
  retryBtn:  { backgroundColor: '#2E7D32', paddingHorizontal: 28, paddingVertical: 12, borderRadius: 20 },
  retryText: { color: '#fff', fontWeight: '700', fontSize: 15 },

  header: {
    backgroundColor: '#fff',
    paddingTop: 54, paddingBottom: 10, paddingHorizontal: 16,
    borderBottomWidth: 1, borderBottomColor: '#e0e0e0',
  },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#111' },
  headerSub:   { fontSize: 12, color: '#666', marginTop: 2 },

  demoBanner: {
    backgroundColor: '#FFF8E1',
    paddingHorizontal: 14, paddingVertical: 8,
    borderBottomWidth: 1, borderBottomColor: '#FFE082',
  },
  demoBannerText: { fontSize: 12, color: '#795548', textAlign: 'center' },

  map: { flex: 1 },

  markerWrapper: { alignItems: 'center' },
  bestTag: { borderRadius: 4, paddingHorizontal: 5, paddingVertical: 2, marginBottom: 3 },
  bestTagText: { color: '#fff', fontSize: 8, fontWeight: '800', letterSpacing: 0.8 },
  markerBubble: {
    backgroundColor: 'rgba(255,255,255,0.97)',
    borderRadius: 8, paddingHorizontal: 7, paddingVertical: 4,
    alignItems: 'center',
    shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 3,
    shadowOffset: { width: 0, height: 2 }, elevation: 4,
    minWidth: 76,
  },
  markerName:  { fontSize: 10, fontWeight: '700' },
  markerPrice: { fontSize: 12, fontWeight: '800', color: '#111', marginTop: 1 },
  markerTail: {
    width: 0, height: 0,
    borderLeftWidth: 5, borderRightWidth: 5, borderTopWidth: 6,
    borderLeftColor: 'transparent', borderRightColor: 'transparent',
    marginTop: -1,
  },

  callout: { width: 200, padding: 10 },
  calloutRank:  { fontSize: 13, fontWeight: '800', marginBottom: 4 },
  calloutLine:  { fontSize: 12, color: '#333', marginBottom: 2 },
  calloutSub:   { fontSize: 11, color: '#777', marginBottom: 2 },
  calloutAddr:  { fontSize: 10, color: '#999', marginTop: 4 },

  panel: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    paddingTop: 14, paddingHorizontal: 16, paddingBottom: 24,
    shadowColor: '#000', shadowOpacity: 0.12, shadowRadius: 8,
    shadowOffset: { width: 0, height: -3 }, elevation: 8,
  },
  panelRow:  { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  rankBadge: {
    width: 38, height: 38, borderRadius: 19,
    alignItems: 'center', justifyContent: 'center', marginRight: 12,
  },
  rankText:    { color: '#fff', fontWeight: '800', fontSize: 13 },
  panelMain:   { flex: 1 },
  panelName:   { fontSize: 18, fontWeight: '800', color: '#111' },
  panelSub:    { fontSize: 12, color: '#555', marginTop: 2 },
  panelRight:  { alignItems: 'flex-end' },
  effectiveCost:      { fontSize: 22, fontWeight: '800', color: '#2E7D32' },
  effectiveCostLabel: { fontSize: 10, color: '#888' },

  noteText: {
    fontSize: 12, color: '#444',
    backgroundColor: '#F1F8E9',
    borderRadius: 8, padding: 8, marginBottom: 12,
  },

  strip: { marginHorizontal: -4 },
  stripCard: {
    backgroundColor: '#fafafa',
    borderRadius: 10, borderWidth: 1, borderColor: '#e0e0e0',
    paddingHorizontal: 10, paddingVertical: 8, marginHorizontal: 4,
    alignItems: 'center', width: 90,
  },
  stripRank:  { fontSize: 11, fontWeight: '700' },
  stripName:  { fontSize: 11, fontWeight: '600', color: '#222', marginTop: 2 },
  stripPrice: { fontSize: 12, fontWeight: '700', color: '#333', marginTop: 2 },
  stripEff:   { fontSize: 10, color: '#666', marginTop: 1 },
});
