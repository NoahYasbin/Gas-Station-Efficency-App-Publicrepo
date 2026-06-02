import React, { useState } from 'react';
import {
  View,
  Text,
  ImageBackground,
  StyleSheet,
  useWindowDimensions,
  ScrollView,
  TouchableOpacity,
  LayoutChangeEvent,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SIM_STATIONS, BEST, rankColor } from '../constants/simStations';
import PriceBubble from '../components/PriceBubble';

// Save the Lewes map screenshot to mobile/assets/map_bg.png
const MAP_IMAGE = require('../../assets/map_bg.png');

export default function SimMapScreen() {
  const { width: screenWidth } = useWindowDimensions();
  const [mapLayout, setMapLayout] = useState({ width: 0, height: 0 });

  const onMapLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setMapLayout({ width, height });
  };

  const bestSavings = SIM_STATIONS
    .filter(s => s.rank !== 1)
    .map(s => s.effectiveCost - BEST.effectiveCost);
  const maxSavings = Math.max(...bestSavings);

  return (
    <View style={styles.container}>
      <StatusBar style="dark" />

      {/* ── Header ── */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>⛽  Gas Finder — Lewes, DE</Text>
        <Text style={styles.headerSub}>28 MPG · 4.5 gal in tank · 13.2 gal cap</Text>
      </View>

      {/* ── Map + Bubbles ── */}
      <View style={styles.mapContainer} onLayout={onMapLayout}>
        <ImageBackground
          source={MAP_IMAGE}
          style={styles.map}
          resizeMode="cover"
        >
          {/* User location dot — roughly center of map */}
          <View
            style={[
              styles.userDot,
              {
                left: mapLayout.width  * 0.47 - 10,
                top:  mapLayout.height * 0.47 - 10,
              },
            ]}
          >
            <View style={styles.userDotInner} />
          </View>

          {/* Station price bubbles */}
          {mapLayout.width > 0 &&
            SIM_STATIONS.map(station => (
              <PriceBubble
                key={station.id}
                station={station}
                containerWidth={mapLayout.width}
                containerHeight={mapLayout.height}
              />
            ))}
        </ImageBackground>
      </View>

      {/* ── Recommendation Panel ── */}
      <View style={styles.panel}>
        <View style={styles.panelRow}>
          <View style={[styles.rankBadge, { backgroundColor: rankColor(1) }]}>
            <Text style={styles.rankText}>#1</Text>
          </View>
          <View style={styles.panelMain}>
            <Text style={styles.panelName}>{BEST.name}</Text>
            <Text style={styles.panelSub}>
              {BEST.distanceMiles.toFixed(1)} mi away · ${BEST.price.toFixed(2)}/gal
            </Text>
          </View>
          <View style={styles.panelRight}>
            <Text style={styles.effectiveCost}>${BEST.effectiveCost.toFixed(2)}</Text>
            <Text style={styles.effectiveCostLabel}>total cost</Text>
          </View>
        </View>

        <Text style={styles.noteText}>
          💡 Saves up to ${maxSavings.toFixed(2)} vs other nearby stations once driving cost is included.
        </Text>

        {/* Ranked list strip */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.strip}>
          {SIM_STATIONS.map(s => (
            <View
              key={s.id}
              style={[
                styles.stripCard,
                s.rank === 1 && { borderColor: rankColor(1), borderWidth: 2 },
              ]}
            >
              <Text style={[styles.stripRank, { color: rankColor(s.rank) }]}>#{s.rank}</Text>
              <Text style={styles.stripName} numberOfLines={1}>{s.name}</Text>
              <Text style={styles.stripPrice}>${s.price.toFixed(2)}</Text>
              <Text style={styles.stripEff}>${s.effectiveCost.toFixed(2)} total</Text>
            </View>
          ))}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },

  // Header
  header: {
    backgroundColor: '#fff',
    paddingTop: 54,
    paddingBottom: 10,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#111' },
  headerSub:   { fontSize: 12, color: '#666', marginTop: 2 },

  // Map
  mapContainer: { flex: 1 },
  map:          { flex: 1 },

  // User location dot
  userDot: {
    position: 'absolute',
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: 'rgba(66,133,244,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  userDotInner: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#4285F4',
    borderWidth: 2,
    borderColor: '#fff',
  },

  // Bottom panel
  panel: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingTop: 14,
    paddingHorizontal: 16,
    paddingBottom: 24,
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: -3 },
    elevation: 8,
  },
  panelRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  rankBadge: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  rankText:    { color: '#fff', fontWeight: '800', fontSize: 13 },
  panelMain:   { flex: 1 },
  panelName:   { fontSize: 18, fontWeight: '800', color: '#111' },
  panelSub:    { fontSize: 12, color: '#555', marginTop: 2 },
  panelRight:  { alignItems: 'flex-end' },
  effectiveCost:      { fontSize: 22, fontWeight: '800', color: '#2E7D32' },
  effectiveCostLabel: { fontSize: 10, color: '#888' },

  noteText: {
    fontSize: 12,
    color: '#444',
    backgroundColor: '#F1F8E9',
    borderRadius: 8,
    padding: 8,
    marginBottom: 12,
  },

  // Horizontal strip
  strip: { marginHorizontal: -4 },
  stripCard: {
    backgroundColor: '#fafafa',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e0e0e0',
    paddingHorizontal: 10,
    paddingVertical: 8,
    marginHorizontal: 4,
    alignItems: 'center',
    width: 90,
  },
  stripRank:  { fontSize: 11, fontWeight: '700' },
  stripName:  { fontSize: 11, fontWeight: '600', color: '#222', marginTop: 2 },
  stripPrice: { fontSize: 12, fontWeight: '700', color: '#333', marginTop: 2 },
  stripEff:   { fontSize: 10, color: '#666', marginTop: 1 },
});
