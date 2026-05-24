import { useEffect, useMemo, useRef } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.heat";
import type { HeatmapResponse, MapaResponse, NivelRisco } from "@/lib/types";

// Fix dos ícones padrão do Leaflet (sem isso, marcadores não aparecem no Vite)
import iconUrl from "leaflet/dist/images/marker-icon.png";
import iconShadow from "leaflet/dist/images/marker-shadow.png";
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";

L.Icon.Default.mergeOptions({
  iconUrl,
  iconRetinaUrl,
  shadowUrl: iconShadow,
});

const COR_RISCO: Record<NivelRisco, string> = {
  baixo: "#64748b",
  moderado: "#facc15",
  alto: "#f97316",
  critico: "#ef4444",
};

function pacienteIcon(nivel: NivelRisco | null): L.DivIcon {
  const cor = nivel ? COR_RISCO[nivel] : "#64748b";
  return L.divIcon({
    className: "",
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${cor};border:2px solid #f1f5f9;box-shadow:0 0 0 2px ${cor}33"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function sedeIcon(cor: string): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="width:18px;height:18px;border-radius:4px;background:${cor};border:2px solid #f1f5f9;display:flex;align-items:center;justify-content:center;color:white;font-size:11px;font-weight:bold">+</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

const RJ_CENTER: [number, number] = [-22.92, -43.4];

function HeatLayer({ pontos }: { pontos: Array<[number, number, number]> }) {
  const map = useMap();
  const layerRef = useRef<L.Layer | null>(null);

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }
    if (!pontos.length) return;
    // @ts-expect-error — leaflet.heat polyfill no namespace L
    const layer = L.heatLayer(pontos, {
      radius: 25,
      blur: 18,
      maxZoom: 17,
      gradient: { 0.2: "#10b981", 0.5: "#f59e0b", 0.8: "#f97316", 1.0: "#ef4444" },
    });
    layer.addTo(map);
    layerRef.current = layer;
    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [pontos, map]);

  return null;
}

function FitBounds({ pontos }: { pontos: Array<{ lat: number; lon: number }> }) {
  const map = useMap();
  useEffect(() => {
    if (!pontos.length) return;
    const b = L.latLngBounds(pontos.map((p) => [p.lat, p.lon] as [number, number]));
    map.fitBounds(b.pad(0.1));
  }, [pontos, map]);
  return null;
}

interface Props {
  mapa: MapaResponse | null;
  heatmap?: HeatmapResponse | null;
  altura?: string;
  mostrarPacientes?: boolean;
  mostrarSedes?: boolean;
}

export function MapaBase({
  mapa,
  heatmap = null,
  altura = "60vh",
  mostrarPacientes = true,
  mostrarSedes = true,
}: Props) {
  const allPontos = useMemo(() => {
    const arr: Array<{ lat: number; lon: number }> = [];
    if (mapa) {
      if (mostrarPacientes) mapa.pacientes.forEach((p) => arr.push({ lat: p.lat, lon: p.lon }));
      if (mostrarSedes) mapa.sedes_equipes.forEach((s) => arr.push({ lat: s.lat, lon: s.lon }));
    }
    return arr;
  }, [mapa, mostrarPacientes, mostrarSedes]);

  return (
    <div className="rounded-2xl overflow-hidden border border-slate-800/60" style={{ height: altura }}>
      <MapContainer
        center={RJ_CENTER}
        zoom={11}
        scrollWheelZoom
        className="h-full w-full"
        style={{ background: "#0f172a" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {heatmap && <HeatLayer pontos={heatmap.pontos} />}
        {mapa && allPontos.length > 0 && <FitBounds pontos={allPontos} />}
        {mapa &&
          mostrarPacientes &&
          mapa.pacientes.map((p) => (
            <Marker
              key={`p-${p.paciente_id}`}
              position={[p.lat, p.lon]}
              icon={pacienteIcon(p.nivel_risco)}
            >
              <Popup>
                <div className="text-xs">
                  <div className="font-medium">{p.nome_display}</div>
                  <div className="text-slate-500">Nível: {p.nivel_risco ?? "—"}</div>
                  <a
                    href={`/pacientes/${p.paciente_id}`}
                    className="text-saude-600 hover:underline"
                  >
                    Abrir Paciente 360 →
                  </a>
                </div>
              </Popup>
            </Marker>
          ))}
        {mapa &&
          mostrarSedes &&
          mapa.sedes_equipes.map((s) => (
            <Marker key={`e-${s.equipe_id}`} position={[s.lat, s.lon]} icon={sedeIcon("#10b981")}>
              <Popup>
                <div className="text-xs">
                  <div className="font-medium">{s.nome}</div>
                  <div className="text-slate-500">Sede da equipe</div>
                </div>
              </Popup>
            </Marker>
          ))}
      </MapContainer>
    </div>
  );
}
