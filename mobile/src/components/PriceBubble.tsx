import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SimStation, rankColor } from '../constants/simStations';

interface Props {
  station: SimStation;
  containerWidth: number;
  containerHeight: number;
}

export default function PriceBubble({ station, containerWidth, containerHeight }: Props) {
  const color = rankColor(station.rank);
  const isBest = station.rank === 1;

  return (
    <View
      style={[
        styles.wrapper,
        {
          left: containerWidth  * station.posX - 52,
          top:  containerHeight * station.posY - 52,
        },
      ]}
    >
      {isBest && (
        <View style={[styles.bestBadge, { backgroundColor: color }]}>
          <Text style={styles.bestText}>BEST</Text>
        </View>
      )}

      <View style={[styles.bubble, { borderColor: color, borderWidth: isBest ? 2.5 : 1.5 }]}>
        <Text style={[styles.name, { color }]} numberOfLines={1}>
          {station.name}
        </Text>
        <Text style={styles.price}>${station.price.toFixed(2)}/gal</Text>
        <Text style={styles.sub}>{station.distanceMiles.toFixed(1)} mi away</Text>
      </View>

      {/* Tail pointing down to the map pin location */}
      <View style={[styles.tail, { borderTopColor: color }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    position: 'absolute',
    alignItems: 'center',
    width: 104,
  },
  bestBadge: {
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginBottom: 3,
  },
  bestText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  bubble: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 5,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 4,
    width: 104,
  },
  name: {
    fontSize: 11,
    fontWeight: '700',
  },
  price: {
    fontSize: 13,
    fontWeight: '800',
    color: '#111',
    marginTop: 1,
  },
  sub: {
    fontSize: 9,
    color: '#666',
    marginTop: 1,
  },
  tail: {
    width: 0,
    height: 0,
    borderLeftWidth: 6,
    borderRightWidth: 6,
    borderTopWidth: 7,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    marginTop: -1,
  },
});
