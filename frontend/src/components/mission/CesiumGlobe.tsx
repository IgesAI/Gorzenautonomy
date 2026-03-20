import { useEffect, useRef } from 'react';
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
} from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

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
}: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);

  // Initialize viewer
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

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
      terrain: undefined,
    });

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

    // Dark atmosphere
    viewer.scene.globe.enableLighting = true;
    viewer.scene.backgroundColor = Color.fromCssColorString('#0a0e1a');
    viewer.scene.globe.baseColor = Color.fromCssColorString('#1a1f35');

    // Initial camera
    const homeLat = homePosition?.lat ?? 41.905;
    const homeLon = homePosition?.lon ?? -84.632;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(homeLon, homeLat, 50000),
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

    // MOUSE_MOVE: update dragged waypoint position
    handler.setInputAction((event: any) => {
      if (!dragging || dragIndex < 0) return;
      const ray = viewer.camera.getPickRay(event.endPosition);
      if (!ray) return;
      const earthPos = viewer.scene.globe.pick(ray, viewer.scene);
      if (!earthPos) return;

      // Update entity position live
      const entity = viewer.entities.values.find(
        (e) => e.name === `WP ${dragIndex}`
      );
      if (entity) {
        entity.position = earthPos as any;
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

    // DOUBLE_CLICK: add waypoint
    handler.setInputAction((event: any) => {
      const cartesian = viewer.camera.pickEllipsoid(
        event.position,
        viewer.scene.globe.ellipsoid
      );
      if (cartesian && onAddWaypoint) {
        const cartographic = Cartographic.fromCartesian(cartesian);
        const lat = CesiumMath.toDegrees(cartographic.latitude);
        const lon = CesiumMath.toDegrees(cartographic.longitude);
        onAddWaypoint(lat, lon, 100);
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
  }, [onAddWaypoint, onRemoveWaypoint, onMoveWaypoint]);

  // Update waypoint entities
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old waypoint entities
    const toRemove: Entity[] = [];
    viewer.entities.values.forEach((e) => {
      if (e.name && (e.name.startsWith('WP ') || e.name === 'flight-path')) {
        toRemove.push(e);
      }
    });
    toRemove.forEach((e) => viewer.entities.remove(e));

    // Add waypoints
    waypoints.forEach((wp, i) => {
      const isFirst = i === 0;
      const isLast = i === waypoints.length - 1 && waypoints.length > 1;

      viewer.entities.add({
        name: `WP ${wp.order}`,
        position: Cartesian3.fromDegrees(wp.longitude_deg, wp.latitude_deg, wp.altitude_m),
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

    // Flight path polyline
    if (waypoints.length >= 2) {
      const positions = waypoints.map((wp) =>
        Cartesian3.fromDegrees(wp.longitude_deg, wp.latitude_deg, wp.altitude_m)
      );
      viewer.entities.add({
        name: 'flight-path',
        polyline: {
          positions,
          width: 3,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.2,
            color: Color.fromCssColorString('#2f7fff').withAlpha(0.8),
          }),
          clampToGround: false,
        },
      });
    }
  }, [waypoints]);

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
      const alt = 200;

      // Arrow shaft
      viewer.entities.add({
        name: 'wind-shaft',
        polyline: {
          positions: [
            Cartesian3.fromDegrees(lon1, lat1, alt),
            Cartesian3.fromDegrees(tipLon, tipLat, alt),
          ],
          width: 4,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.25,
            color: windColor.withAlpha(0.8),
          }),
          clampToGround: false,
        },
      });

      // Left barb
      viewer.entities.add({
        name: 'wind-barb-l',
        polyline: {
          positions: [
            Cartesian3.fromDegrees(tipLon, tipLat, alt),
            Cartesian3.fromDegrees(tipLon + barbL.dLon, tipLat + barbL.dLat, alt),
          ],
          width: 4,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.25,
            color: windColor.withAlpha(0.8),
          }),
          clampToGround: false,
        },
      });

      // Right barb
      viewer.entities.add({
        name: 'wind-barb-r',
        polyline: {
          positions: [
            Cartesian3.fromDegrees(tipLon, tipLat, alt),
            Cartesian3.fromDegrees(tipLon + barbR.dLon, tipLat + barbR.dLat, alt),
          ],
          width: 4,
          material: new PolylineGlowMaterialProperty({
            glowPower: 0.25,
            color: windColor.withAlpha(0.8),
          }),
          clampToGround: false,
        },
      });

      // Speed label at tip
      viewer.entities.add({
        name: 'wind-label',
        position: Cartesian3.fromDegrees(tipLon, tipLat, alt),
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
