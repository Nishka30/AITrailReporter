"use client";

import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import Link from "next/link";
import { useEffect } from "react";

// Custom brand-colored dot marker -- sidesteps Leaflet's well-known
// bundler-asset-path issue with its default marker PNGs (no image asset
// needed at all), and matches the product's warm/marigold palette instead
// of Leaflet's stock blue pin.
function dotIcon(highlight: boolean) {
  return L.divIcon({
    className: "",
    html: `<span style="display:block;width:16px;height:16px;border-radius:999px;background:${
      highlight ? "#b8391f" : "#e8a13c"
    };border:2px solid #faf4e9;box-shadow:0 1px 4px rgba(33,26,20,0.35)"></span>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

export interface MapPin {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  href?: string;
  highlight?: boolean;
}

function FitBounds({ pins }: { pins: MapPin[] }) {
  const map = useMap();
  useEffect(() => {
    if (pins.length === 0) return;
    if (pins.length === 1) {
      map.setView([pins[0].latitude, pins[0].longitude], 11);
      return;
    }
    map.fitBounds(pins.map((p) => [p.latitude, p.longitude]), { padding: [32, 32] });
  }, [pins, map]);
  return null;
}

export function MapView({ pins, height = 360 }: { pins: MapPin[]; height?: number }) {
  if (pins.length === 0) return null;
  const center: [number, number] = [pins[0].latitude, pins[0].longitude];

  return (
    <div style={{ height }} className="overflow-hidden rounded-3xl border border-border">
      <MapContainer center={center} zoom={10} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds pins={pins} />
        {pins.map((pin) => (
          <Marker key={pin.id} position={[pin.latitude, pin.longitude]} icon={dotIcon(Boolean(pin.highlight))}>
            <Popup>
              <span className="font-medium">{pin.name}</span>
              {pin.href && (
                <>
                  <br />
                  <Link href={pin.href} className="text-marigold-deep underline">
                    View place
                  </Link>
                </>
              )}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
