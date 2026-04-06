import { useEffect, useRef } from 'react';
import type { Scene } from 'cesium';
import {
  Viewer,
  Cartesian3,
  Color,
  Entity,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  defined,
  HeightReference,
  PolylineGlowMaterialProperty,
  VerticalOrigin,
  LabelStyle,
  Cartographic,
  Math as CesiumMath,
  UrlTemplateImageryProvider,
  HorizontalOrigin,
  Ion,
  Terrain,
  JulianDate,
  DynamicAtmosphereLightingType,
  Tonemapper,
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import { haversineMeters, initialBearingDeg } from '../../utils/geo';

const FLIGHT_CAT_HEX: Record<string, string> = {
  VFR: '#10b981',
  MVFR: '#3b82f6',
  IFR: '#f59e0b',
  LIFR: '#ef4444',
};

/** Ellipsoid height (m) for wind graphics: terrain + AGL, or a safe default if tiles not ready. */
function windHeightMetersAboveGround(
  scene: Scene,
  lonDeg: number,
  latDeg: number,
  aglM: number,
): number {
  const c = Cartographic.fromDegrees(lonDeg, latDeg);
  const h = scene.globe.getHeight(c);
  if (h !== undefined && Number.isFinite(h)) {
    return h + aglM;
  }
  return Math.max(aglM, 2500);
}

/**
 * Waypoint `altitude_m` is relative to home/takeoff (backend), not ellipsoid height.
 * Cesium uses ellipsoid meters — use terrain height at home + relative offset (see PX4/QGC convention).
 * Without home, approximate as terrain at waypoint + relative (AGL-style).
 */
function ellipsoidHeightForMissionWaypoint(
  scene: Scene,
  wp: GlobeWaypoint,
  home: { lon: number; lat: number } | null | undefined,
): number {
  if (home) {
    const cHome = Cartographic.fromDegrees(home.lon, home.lat);
    const hHome = scene.globe.getHeight(cHome);
    const base = hHome !== undefined && Number.isFinite(hHome) ? hHome : 0;
    return base + wp.altitude_m;
  }
  const cWp = Cartographic.fromDegrees(wp.longitude_deg, wp.latitude_deg);
  const hWp = scene.globe.getHeight(cWp);
  const g = hWp !== undefined && Number.isFinite(hWp) ? hWp : 0;
  return g + wp.altitude_m;
}

export interface GlobeWaypoint {
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number;
  order: number;
  speed_ms?: number;
  loiter_time_s?: number;
  camera_action?: string;
}

export interface WeatherOverlay {
  temperature_c: number;
  wind_speed_ms: number;
  wind_direction_deg: number;
  pressure_hpa: number;
  density_altitude_ft: number;
  flight_category: string;
  humidity_pct?: number;
  visibility_km?: number;
}

export interface CesiumViewerApi {
  captureScreenshot: () => string | undefined;
}

interface CesiumGlobeProps {
  waypoints: GlobeWaypoint[];
  dronePosition?: { lat: number; lon: number; alt: number } | null;
  operatorPosition?: { lat: number; lon: number } | null;
  weather?: WeatherOverlay | null;
  onAddWaypoint?: (lat: number, lon: number, alt: number) => void;
  onRemoveWaypoint?: (index: number) => void;
  onMoveWaypoint?: (index: number, lat: number, lon: number) => void;
  onFlyTo?: (fn: () => void) => void;
  homePosition?: { lat: number; lon: number } | null;
  geofenceRadius?: number; // meters, 0 = no geofence
  /** Mission default altitude (m) passed through on double-click add. */
  defaultAddAltitude?: number;
  /** Server-computed leg lengths (m); length should be waypoints.length - 1. */
  legDistancesM?: number[] | null;
  onViewerReady?: (api: CesiumViewerApi) => void;
}

export function CesiumGlobe({
  waypoints,
  dronePosition,
  operatorPosition,
  weather,
  onAddWaypoint,
  onRemoveWaypoint,
  onMoveWaypoint,
  onFlyTo,
  homePosition,
  geofenceRadius = 0,
  defaultAddAltitude = 100,
  legDistancesM = null,
  onViewerReady,
}: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);
  const waypointsRef = useRef(waypoints);
  waypointsRef.current = waypoints;
  const homePositionRef = useRef(homePosition);
  homePositionRef.current = homePosition;

  // Initialize viewer
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    const ionTok = import.meta.env.VITE_CESIUM_ION_TOKEN;
    if (ionTok) {
      Ion.defaultAccessToken = ionTok;
    }

    const viewer = new Viewer(containerRef.current, {
      animation: false,
      baseLayerPicker: false,
      fullscreenButton: false,
      vrButton: false,
      geocoder: false,
      homeButton: false,
      infoBox: false,
      sceneModePicker: false,
      selectionIndicator: false,
      timeline: false,
      navigationHelpButton: false,
      creditContainer: document.createElement('div'),
      // Crisp rendering on high-DPI displays — resolutionScale set on viewer below.
      useBrowserRecommendedResolution: false,
      terrain: ionTok
        ? Terrain.fromWorldTerrain({
            requestVertexNormals: true,
            requestWaterMask: true,
          })
        : undefined,
    });

    viewer.clock.currentTime = JulianDate.now();
    viewer.clock.shouldAnimate = true;
    viewer.clock.multiplier = 1;

    viewer.resolutionScale = Math.min(
      typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1,
      2,
    );

    const scene = viewer.scene;
    // Sun-linked sky/atmosphere (pairs with globe lighting + animated clock). See Cesium DynamicAtmosphereLightingType.
    scene.atmosphere.dynamicLighting = DynamicAtmosphereLightingType.SUNLIGHT;
    // Slightly richer limb / fog without washing out the dark chrome theme.
    scene.atmosphere.brightnessShift = 0.06;
    scene.atmosphere.saturationShift = -0.05;

    if (scene.highDynamicRangeSupported) {
      scene.highDynamicRange = true;
      scene.postProcessStages.tonemapper = Tonemapper.ACES;
      scene.postProcessStages.exposure = 1.05;
    }
    scene.postProcessStages.fxaa.enabled = true;
    scene.sunBloom = true;
    if (scene.msaaSupported) {
      scene.msaaSamples = 4;
    }
    if (ionTok) {
      // Occlude vectors against terrain; camera stays above ground mesh.
      scene.globe.depthTestAgainstTerrain = true;
      scene.screenSpaceCameraController.enableCollisionDetection = true;
      // Sharper terrain LOD than default (2); modest GPU cost.
      scene.globe.maximumScreenSpaceError = 1.5;
      // Water shimmer where terrain provides a water mask.
      scene.globe.showWaterEffect = true;
      // Slightly lighter horizon fog than default so terrain stays readable at range.
      scene.fog.visualDensityScalar = 0.55;
    }

    // Satellite imagery base + label overlay on top
    viewer.imageryLayers.removeAll();

    // Base: satellite imagery (ESRI World Imagery - free, no key required)
    viewer.imageryLayers.addImageryProvider(
      new UrlTemplateImageryProvider({
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        maximumLevel: 19,
        credit: 'Esri, Maxar, Earthstar Geographics',
      })
    );

    // Overlay: labels only (CartoDB dark labels - roads, cities, landmarks, water names)
    const labelLayer = viewer.imageryLayers.addImageryProvider(
      new UrlTemplateImageryProvider({
        url: 'https://basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png',
        maximumLevel: 18,
        credit: 'CartoDB',
      })
    );
    labelLayer.alpha = 0.9;

    // Dark space + lit globe (terrain normals + sun).
    scene.globe.enableLighting = true;
    scene.globe.showGroundAtmosphere = true;
    scene.backgroundColor = Color.fromCssColorString('#0a0e1a');
    scene.globe.baseColor = Color.fromCssColorString('#1a1f35');

    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(-84.632, 41.905, 50000),
      duration: 0,
    });

    viewerRef.current = viewer;

    return () => {
      if (handlerRef.current) {
        handlerRef.current.destroy();
        handlerRef.current = null;
      }
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !onViewerReady) return;
    onViewerReady({
      captureScreenshot: () => {
        viewer.render();
        try {
          return viewer.scene.canvas.toDataURL('image/png');
        } catch {
          return undefined;
        }
      },
    });
  }, [onViewerReady]);

  // Fly to home position when it changes
  useEffect(() => {
    if (!viewerRef.current || !homePosition) return;
    viewerRef.current.camera.flyTo({
      destination: Cartesian3.fromDegrees(homePosition.lon, homePosition.lat, 2000),
      duration: 2.0,
    });
  }, [homePosition]);

  // Interaction handlers: drag-to-move, double-click-to-add, right-click-to-remove
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    if (handlerRef.current) {
      handlerRef.current.destroy();
    }

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handlerRef.current = handler;

    let dragging = false;
    let dragIndex = -1;

    // LEFT_DOWN: pick a waypoint to start dragging
    handler.setInputAction((event: any) => {
      const picked = viewer.scene.pick(event.position);
      if (defined(picked) && picked.id && typeof picked.id.name === 'string') {
        const match = picked.id.name.match(/^WP (\d+)/);
        if (match) {
          dragging = true;
          dragIndex = parseInt(match[1], 10);
          viewer.scene.screenSpaceCameraController.enableRotate = false;
          viewer.scene.screenSpaceCameraController.enableTranslate = false;
          viewer.scene.screenSpaceCameraController.enableZoom = false;
        }
      }
    }, ScreenSpaceEventType.LEFT_DOWN);

    // MOUSE_MOVE: update dragged waypoint position (keep mission altitude, not terrain surface)
    handler.setInputAction((event: any) => {
      if (!dragging || dragIndex < 0) return;
      const ray = viewer.camera.getPickRay(event.endPosition);
      if (!ray) return;
      const earthPos = viewer.scene.globe.pick(ray, viewer.scene);
      if (!earthPos) return;

      const wp = waypointsRef.current.find((w) => w.order === dragIndex);
      if (!wp) return;
      const z = ellipsoidHeightForMissionWaypoint(
        viewer.scene,
        wp,
        homePositionRef.current,
      );
      const carto = Cartographic.fromCartesian(earthPos);
      carto.height = z;
      const atMissionAlt = Cartographic.toCartesian(carto);

      const entity = viewer.entities.values.find(
        (e) => e.name === `WP ${dragIndex}`
      );
      if (entity) {
        entity.position = atMissionAlt as any;
      }
    }, ScreenSpaceEventType.MOUSE_MOVE);

    // LEFT_UP: finish drag, commit position
    handler.setInputAction((event: any) => {
      if (dragging && dragIndex >= 0 && onMoveWaypoint) {
        const ray = viewer.camera.getPickRay(event.position);
        if (ray) {
          const earthPos = viewer.scene.globe.pick(ray, viewer.scene);
          if (earthPos) {
            const carto = Cartographic.fromCartesian(earthPos);
            onMoveWaypoint(
              dragIndex,
              CesiumMath.toDegrees(carto.latitude),
              CesiumMath.toDegrees(carto.longitude),
            );
          }
        }
      }
      if (dragging) {
        dragging = false;
        dragIndex = -1;
        viewer.scene.screenSpaceCameraController.enableRotate = true;
        viewer.scene.screenSpaceCameraController.enableTranslate = true;
        viewer.scene.screenSpaceCameraController.enableZoom = true;
      }
    }, ScreenSpaceEventType.LEFT_UP);

    // DOUBLE_CLICK: add waypoint (terrain-aware pick, ellipsoid fallback)
    handler.setInputAction((event: any) => {
      if (!onAddWaypoint) return;
      const ray = viewer.camera.getPickRay(event.position);
      let cartesian: Cartesian3 | undefined;
      if (ray) {
        cartesian = viewer.scene.globe.pick(ray, viewer.scene);
      }
      if (!cartesian) {
        cartesian = viewer.camera.pickEllipsoid(
          event.position,
          viewer.scene.globe.ellipsoid,
        );
      }
      if (cartesian) {
        const cartographic = Cartographic.fromCartesian(cartesian);
        const lat = CesiumMath.toDegrees(cartographic.latitude);
        const lon = CesiumMath.toDegrees(cartographic.longitude);
        onAddWaypoint(lat, lon, defaultAddAltitude);
      }
    }, ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

    // RIGHT_CLICK: remove waypoint
    handler.setInputAction((event: any) => {
      const picked = viewer.scene.pick(event.position);
      if (defined(picked) && picked.id && typeof picked.id.name === 'string') {
        const match = picked.id.name.match(/^WP (\d+)/);
        if (match && onRemoveWaypoint) {
          onRemoveWaypoint(parseInt(match[1], 10));
        }
      }
    }, ScreenSpaceEventType.RIGHT_CLICK);
  }, [onAddWaypoint, onRemoveWaypoint, onMoveWaypoint, defaultAddAltitude]);

  // Update waypoint entities
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old waypoint + path + leg label entities
    const toRemove: Entity[] = [];
    viewer.entities.values.forEach((e) => {
      if (
        e.name &&
        (e.name.startsWith('WP ') ||
          e.name === 'flight-path' ||
          e.name.startsWith('leg-label-'))
      ) {
        toRemove.push(e);
      }
    });
    toRemove.forEach((e) => viewer.entities.remove(e));

    const scene = viewer.scene;

    // Add waypoints
    waypoints.forEach((wp, i) => {
      const isFirst = i === 0;
      const isLast = i === waypoints.length - 1 && waypoints.length > 1;
      const z = ellipsoidHeightForMissionWaypoint(scene, wp, homePosition);

      viewer.entities.add({
        name: `WP ${wp.order}`,
        position: Cartesian3.fromDegrees(wp.longitude_deg, wp.latitude_deg, z),
        point: {
          pixelSize: isFirst || isLast ? 12 : 8,
          color: isFirst
            ? Color.fromCssColorString('#10b981')
            : isLast
            ? Color.fromCssColorString('#ef4444')
            : Color.fromCssColorString('#2f7fff'),
          outlineColor: Color.WHITE.withAlpha(0.4),
          outlineWidth: 1,
          heightReference: HeightReference.NONE,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: `${wp.order}`,
          font: '11px monospace',
          fillColor: Color.WHITE.withAlpha(0.9),
          outlineColor: Color.BLACK.withAlpha(0.7),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: new Cartesian3(0, -14, 0) as any,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    });

    // Flight path polyline + per-leg distance / bearing labels
    if (waypoints.length >= 2) {
      const positions = waypoints.map((wp) => {
        const z = ellipsoidHeightForMissionWaypoint(scene, wp, homePosition);
        return Cartesian3.fromDegrees(wp.longitude_deg, wp.latitude_deg, z);
      });
      const flightMat = new PolylineGlowMaterialProperty({
        glowPower: 0.2,
        color: Color.fromCssColorString('#2f7fff').withAlpha(0.8),
      });
      viewer.entities.add({
        name: 'flight-path',
        polyline: {
          positions,
          width: 3,
          material: flightMat,
          depthFailMaterial: flightMat,
          clampToGround: false,
        },
      });

      for (let i = 0; i < waypoints.length - 1; i++) {
        const a = waypoints[i];
        const b = waypoints[i + 1];
        const midLat = (a.latitude_deg + b.latitude_deg) / 2;
        const midLon = (a.longitude_deg + b.longitude_deg) / 2;
        const za = ellipsoidHeightForMissionWaypoint(scene, a, homePosition);
        const zb = ellipsoidHeightForMissionWaypoint(scene, b, homePosition);
        const midAlt = (za + zb) / 2;
        let distM: number;
        if (
          legDistancesM &&
          legDistancesM[i] != null &&
          Number.isFinite(legDistancesM[i])
        ) {
          distM = legDistancesM[i];
        } else {
          distM = haversineMeters(
            { lat: a.latitude_deg, lon: a.longitude_deg },
            { lat: b.latitude_deg, lon: b.longitude_deg },
          );
        }
        const brg = initialBearingDeg(
          a.latitude_deg,
          a.longitude_deg,
          b.latitude_deg,
          b.longitude_deg,
        );
        const km =
          distM >= 1000
            ? `${(distM / 1000).toFixed(2)} km`
            : `${distM.toFixed(0)} m`;
        const text = `${km} · ${brg.toFixed(0).padStart(3, '0')}°`;
        viewer.entities.add({
          name: `leg-label-${i}`,
          position: Cartesian3.fromDegrees(midLon, midLat, midAlt),
          label: {
            text,
            font: '9px monospace',
            fillColor: Color.WHITE.withAlpha(0.85),
            outlineColor: Color.BLACK.withAlpha(0.75),
            outlineWidth: 2,
            style: LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: VerticalOrigin.CENTER,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
      }
    }
  }, [waypoints, legDistancesM, homePosition]);

  // Update drone position
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old drone entity
    const existing = viewer.entities.values.find((e) => e.name === 'drone-live');
    if (existing) viewer.entities.remove(existing);

    if (dronePosition) {
      viewer.entities.add({
        name: 'drone-live',
        position: Cartesian3.fromDegrees(dronePosition.lon, dronePosition.lat, dronePosition.alt),
        point: {
          pixelSize: 14,
          color: Color.fromCssColorString('#f59e0b'),
          outlineColor: Color.WHITE.withAlpha(0.6),
          outlineWidth: 2,
          heightReference: HeightReference.NONE,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: 'DRONE',
          font: 'bold 10px monospace',
          fillColor: Color.fromCssColorString('#f59e0b'),
          outlineColor: Color.BLACK.withAlpha(0.7),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: new Cartesian3(0, -18, 0) as any,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }
  }, [dronePosition]);

  // Update operator (GPS) position
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const existing = viewer.entities.values.find((e) => e.name === 'operator-gps');
    if (existing) viewer.entities.remove(existing);

    if (operatorPosition) {
      viewer.entities.add({
        name: 'operator-gps',
        position: Cartesian3.fromDegrees(operatorPosition.lon, operatorPosition.lat, 0),
        point: {
          pixelSize: 10,
          color: Color.fromCssColorString('#06b6d4'),
          outlineColor: Color.WHITE.withAlpha(0.5),
          outlineWidth: 2,
          heightReference: HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: {
          text: 'YOU',
          font: 'bold 10px monospace',
          fillColor: Color.fromCssColorString('#06b6d4'),
          outlineColor: Color.BLACK.withAlpha(0.7),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          pixelOffset: new Cartesian3(0, -16, 0) as any,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        ellipse: {
          semiMajorAxis: 150,
          semiMinorAxis: 150,
          material: Color.fromCssColorString('#06b6d4').withAlpha(0.08),
          outline: true,
          outlineColor: Color.fromCssColorString('#06b6d4').withAlpha(0.25),
          heightReference: HeightReference.CLAMP_TO_GROUND,
        },
      });
    }
  }, [operatorPosition]);

  // Geofence circle around home/operator position
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const existing = viewer.entities.values.find((e) => e.name === 'geofence');
    if (existing) viewer.entities.remove(existing);
    const existingLabel = viewer.entities.values.find((e) => e.name === 'geofence-label');
    if (existingLabel) viewer.entities.remove(existingLabel);

    if (geofenceRadius > 0 && operatorPosition) {
      viewer.entities.add({
        name: 'geofence',
        position: Cartesian3.fromDegrees(operatorPosition.lon, operatorPosition.lat, 0),
        ellipse: {
          semiMajorAxis: geofenceRadius,
          semiMinorAxis: geofenceRadius,
          material: Color.fromCssColorString('#f59e0b').withAlpha(0.04),
          outline: true,
          outlineColor: Color.fromCssColorString('#f59e0b').withAlpha(0.4),
          outlineWidth: 2,
          heightReference: HeightReference.CLAMP_TO_GROUND,
        },
      });
      // Label at the edge
      const edgeLat = operatorPosition.lat + (geofenceRadius / 111320);
      viewer.entities.add({
        name: 'geofence-label',
        position: Cartesian3.fromDegrees(operatorPosition.lon, edgeLat, 0),
        label: {
          text: `GEOFENCE ${geofenceRadius}m`,
          font: 'bold 9px monospace',
          fillColor: Color.fromCssColorString('#f59e0b').withAlpha(0.7),
          outlineColor: Color.BLACK.withAlpha(0.6),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }
  }, [geofenceRadius, operatorPosition]);

  // Flight category + temperature (near operator, offset from "YOU")
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const existing = viewer.entities.values.find((e) => e.name === 'weather-cat-label');
    if (existing) viewer.entities.remove(existing);

    if (weather && operatorPosition) {
      const hex = FLIGHT_CAT_HEX[weather.flight_category] ?? '#94a3b8';
      const lat = operatorPosition.lat + 0.0022;
      const lon = operatorPosition.lon;
      const zCat = windHeightMetersAboveGround(viewer.scene, lon, lat, 180);
      viewer.entities.add({
        name: 'weather-cat-label',
        position: Cartesian3.fromDegrees(lon, lat, zCat),
        label: {
          text: `${weather.flight_category} · ${weather.temperature_c.toFixed(0)}°C`,
          font: 'bold 10px monospace',
          fillColor: Color.fromCssColorString(hex),
          outlineColor: Color.BLACK.withAlpha(0.75),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }
  }, [weather, operatorPosition]);

  // Wind direction arrow at operator location
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old wind entities
    const toRemove: Entity[] = [];
    viewer.entities.values.forEach((e) => {
      if (e.name && e.name.startsWith('wind-')) toRemove.push(e);
    });
    toRemove.forEach((e) => viewer.entities.remove(e));

    if (weather && operatorPosition && weather.wind_speed_ms > 0) {
      // Wind blows FROM wind_direction_deg, arrow points in the direction wind is going
      const windRad = ((weather.wind_direction_deg + 180) % 360) * Math.PI / 180;
      const arrowLen = Math.min(weather.wind_speed_ms * 80, 3000);
      const lat1 = operatorPosition.lat;
      const lon1 = operatorPosition.lon;
      const cosLat = Math.cos(lat1 * Math.PI / 180);

      // Helper: offset from origin by distance at angle
      const offset = (dist: number, angle: number) => ({
        dLat: (dist / 111320) * Math.cos(angle),
        dLon: (dist / (111320 * cosLat)) * Math.sin(angle),
      });

      // Shaft: from origin to tip
      const tip = offset(arrowLen, windRad);
      const tipLon = lon1 + tip.dLon;
      const tipLat = lat1 + tip.dLat;

      // Arrowhead barbs: two lines angling back from the tip
      const barbLen = arrowLen * 0.3;
      const barbAngle = 0.45; // ~25 degrees spread
      const barbL = offset(barbLen, windRad + Math.PI - barbAngle);
      const barbR = offset(barbLen, windRad + Math.PI + barbAngle);

      const windColor = Color.fromCssColorString('#38bdf8');
      const scene = viewer.scene;
      const agl = 220;
      const z = (lon: number, lat: number) =>
        windHeightMetersAboveGround(scene, lon, lat, agl);
      const z1 = z(lon1, lat1);
      const zTip = z(tipLon, tipLat);
      const zBarbL = z(tipLon + barbL.dLon, tipLat + barbL.dLat);
      const zBarbR = z(tipLon + barbR.dLon, tipLat + barbR.dLat);

      const shaftMat = new PolylineGlowMaterialProperty({
        glowPower: 0.25,
        color: windColor.withAlpha(0.8),
      });

      // Arrow shaft (per-vertex terrain + AGL so the arrow stays above ground in mountains)
      viewer.entities.add({
        name: 'wind-shaft',
        polyline: {
          positions: [
            Cartesian3.fromDegrees(lon1, lat1, z1),
            Cartesian3.fromDegrees(tipLon, tipLat, zTip),
          ],
          width: 4,
          material: shaftMat,
          depthFailMaterial: shaftMat,
          clampToGround: false,
        },
      });

      const barbMat = new PolylineGlowMaterialProperty({
        glowPower: 0.25,
        color: windColor.withAlpha(0.8),
      });

      // Left barb
      viewer.entities.add({
        name: 'wind-barb-l',
        polyline: {
          positions: [
            Cartesian3.fromDegrees(tipLon, tipLat, zTip),
            Cartesian3.fromDegrees(tipLon + barbL.dLon, tipLat + barbL.dLat, zBarbL),
          ],
          width: 4,
          material: barbMat,
          depthFailMaterial: barbMat,
          clampToGround: false,
        },
      });

      // Right barb
      viewer.entities.add({
        name: 'wind-barb-r',
        polyline: {
          positions: [
            Cartesian3.fromDegrees(tipLon, tipLat, zTip),
            Cartesian3.fromDegrees(tipLon + barbR.dLon, tipLat + barbR.dLat, zBarbR),
          ],
          width: 4,
          material: barbMat,
          depthFailMaterial: barbMat,
          clampToGround: false,
        },
      });

      // Speed label at tip
      viewer.entities.add({
        name: 'wind-label',
        position: Cartesian3.fromDegrees(tipLon, tipLat, zTip),
        label: {
          text: `WIND ${weather.wind_speed_ms.toFixed(1)} m/s`,
          font: 'bold 10px monospace',
          fillColor: windColor,
          outlineColor: Color.BLACK.withAlpha(0.8),
          outlineWidth: 2,
          style: LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: VerticalOrigin.BOTTOM,
          horizontalOrigin: HorizontalOrigin.LEFT,
          pixelOffset: new Cartesian3(8, -6, 0) as any,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }
  }, [weather, operatorPosition]);

  // Expose flyToOperator via callback prop
  useEffect(() => {
    if (!onFlyTo) return;
    onFlyTo(() => {
      const viewer = viewerRef.current;
      if (!viewer || !operatorPosition) return;
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(operatorPosition.lon, operatorPosition.lat, 5000),
        duration: 1.5,
      });
    });
  }, [onFlyTo, operatorPosition]);

  return (
    <div ref={containerRef} className="w-full h-full" style={{ minHeight: 400 }} />
  );
}
