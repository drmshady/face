/** ForkStlViewer: 3D viewer for fork STL with hex post markers and click-to-place. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import type { HexPostMarker3D, Point3D } from "../types";

export interface PlacedTag {
  tag_id: number;
  center: Point3D;
  normal: Point3D;
}

export type PlacingMode =
  | { type: "tag"; id: number }
  | { type: "hex" }
  | null;

interface ForkStlViewerProps {
  stlBlob: Blob | null;
  markers: HexPostMarker3D[];
  placedTags: PlacedTag[];
  placingMode: PlacingMode;
  onTagPlaced: (tagId: number, center: Point3D, normal: Point3D) => void;
  onHexPlaced?: (center: Point3D, normal: Point3D) => void;
}

function ForkMesh({
  geometry,
  placingMode,
  onTagPlaced,
  onHexPlaced,
}: {
  geometry: THREE.BufferGeometry;
  placingMode: PlacingMode;
  onTagPlaced: (tagId: number, center: Point3D, normal: Point3D) => void;
  onHexPlaced?: (center: Point3D, normal: Point3D) => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const { camera, raycaster, gl } = useThree();

  const handleClick = useCallback(
    (event: MouseEvent) => {
      if (!placingMode || !meshRef.current) return;

      const rect = gl.domElement.getBoundingClientRect();
      const mouse = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1,
      );

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObject(meshRef.current);

      const hit = intersects[0];
      if (hit) {
        const point = hit.point;
        const normal = hit.face
          ? hit.face.normal
              .clone()
              .applyMatrix3(
                new THREE.Matrix3().getNormalMatrix(meshRef.current.matrixWorld),
              )
              .normalize()
          : new THREE.Vector3(0, 0, 1);

        const center = { x: point.x, y: point.y, z: point.z };
        const norm = { x: normal.x, y: normal.y, z: normal.z };

        if (placingMode.type === "tag") {
          onTagPlaced(placingMode.id, center, norm);
        } else if (placingMode.type === "hex") {
          onHexPlaced?.(center, norm);
        }
      }
    },
    [placingMode, camera, raycaster, gl, onTagPlaced, onHexPlaced],
  );

  useEffect(() => {
    const canvas = gl.domElement;
    canvas.addEventListener("click", handleClick);
    return () => canvas.removeEventListener("click", handleClick);
  }, [gl, handleClick]);

  // Change cursor when in placement mode
  useEffect(() => {
    gl.domElement.style.cursor = placingMode !== null ? "crosshair" : "default";
    return () => {
      gl.domElement.style.cursor = "default";
    };
  }, [placingMode, gl]);

  return (
    <mesh ref={meshRef} geometry={geometry}>
      <meshStandardMaterial
        color="#b0b0b0"
        metalness={0.3}
        roughness={0.6}
      />
    </mesh>
  );
}

/** Auto-frame the camera to look at the mesh bounding box center. */
function CameraFramer({ geometry }: { geometry: THREE.BufferGeometry }) {
  const { camera } = useThree();
  const framed = useRef(false);

  useEffect(() => {
    if (framed.current) return;
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    if (!box) return;

    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);

    camera.position.set(
      center.x + maxDim * 0.6,
      center.y + maxDim * 0.5,
      center.z + maxDim * 0.8,
    );
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    framed.current = true;
  }, [geometry, camera]);

  return null;
}

/** RGB axis arrows at the STL origin (0,0,0). */
function OriginAxes() {
  const axisLength = 15;
  return (
    <group>
      {/* X axis — red */}
      <arrowHelper
        args={[
          new THREE.Vector3(1, 0, 0),
          new THREE.Vector3(0, 0, 0),
          axisLength,
          0xff0000,
          axisLength * 0.15,
          axisLength * 0.08,
        ]}
      />
      {/* Y axis — green */}
      <arrowHelper
        args={[
          new THREE.Vector3(0, 1, 0),
          new THREE.Vector3(0, 0, 0),
          axisLength,
          0x00ff00,
          axisLength * 0.15,
          axisLength * 0.08,
        ]}
      />
      {/* Z axis — blue */}
      <arrowHelper
        args={[
          new THREE.Vector3(0, 0, 1),
          new THREE.Vector3(0, 0, 0),
          axisLength,
          0x0000ff,
          axisLength * 0.15,
          axisLength * 0.08,
        ]}
      />
      {/* Small sphere at origin */}
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>
    </group>
  );
}

function HexPostMarkerViz({ marker }: { marker: HexPostMarker3D }) {
  const color =
    marker.confidence >= 0.7
      ? "#22c55e"
      : marker.confidence >= 0.4
        ? "#eab308"
        : "#ef4444";

  // Rotate from default Y-up to the marker's surface normal
  const quaternion = useMemo(() => {
    const normal = new THREE.Vector3(
      marker.top_face_normal.x,
      marker.top_face_normal.y,
      marker.top_face_normal.z,
    ).normalize();
    const q = new THREE.Quaternion();
    q.setFromUnitVectors(new THREE.Vector3(0, 1, 0), normal);
    return q;
  }, [marker.top_face_normal]);

  // Offset position so the cylinder base sits at the center point,
  // with the body extending outward along the normal
  const position = useMemo(() => {
    const normal = new THREE.Vector3(
      marker.top_face_normal.x,
      marker.top_face_normal.y,
      marker.top_face_normal.z,
    ).normalize();
    return new THREE.Vector3(
      marker.center.x + normal.x * marker.height_mm / 2,
      marker.center.y + normal.y * marker.height_mm / 2,
      marker.center.z + normal.z * marker.height_mm / 2,
    );
  }, [marker.center, marker.top_face_normal, marker.height_mm]);

  return (
    <group position={position} quaternion={quaternion}>
      {/* Cylinder to represent the hex post */}
      <mesh>
        <cylinderGeometry args={[marker.radius_mm, marker.radius_mm, marker.height_mm, 6]} />
        <meshStandardMaterial color={color} transparent opacity={0.7} />
      </mesh>
      {/* Outline ring on top */}
      <mesh position={[0, marker.height_mm / 2, 0]}>
        <ringGeometry args={[marker.radius_mm * 0.8, marker.radius_mm * 1.1, 6]} />
        <meshBasicMaterial color={color} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function TagMarker({ tag }: { tag: PlacedTag }) {
  const quaternion = useMemo(() => {
    const normal = new THREE.Vector3(
      tag.normal.x,
      tag.normal.y,
      tag.normal.z,
    ).normalize();
    const q = new THREE.Quaternion();
    q.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
    return q;
  }, [tag.normal]);

  return (
    <group
      position={[tag.center.x, tag.center.y, tag.center.z]}
      quaternion={quaternion}
    >
      {/* Tag square */}
      <mesh>
        <planeGeometry args={[7, 7]} />
        <meshStandardMaterial
          color={tag.tag_id === 0 ? "#3b82f6" : "#f97316"}
          transparent
          opacity={0.6}
          side={THREE.DoubleSide}
        />
      </mesh>
      {/* Border */}
      <lineSegments>
        <edgesGeometry
          args={[new THREE.PlaneGeometry(7, 7)]}
        />
        <lineBasicMaterial
          color={tag.tag_id === 0 ? "#1d4ed8" : "#c2410c"}
          linewidth={2}
        />
      </lineSegments>
      {/* Normal arrow */}
      <arrowHelper
        args={[
          new THREE.Vector3(0, 0, 1),
          new THREE.Vector3(0, 0, 0),
          8,
          tag.tag_id === 0 ? 0x3b82f6 : 0xf97316,
        ]}
      />
    </group>
  );
}

export function ForkStlViewer({
  stlBlob,
  markers,
  placedTags,
  placingMode,
  onTagPlaced,
  onHexPlaced,
}: ForkStlViewerProps) {
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stlBlob) {
      setGeometry(null);
      return;
    }

    const loader = new STLLoader();
    stlBlob
      .arrayBuffer()
      .then((buffer) => {
        try {
          const geom = loader.parse(buffer);
          geom.computeVertexNormals();
          // Don't center — keep STL's original coordinate system so
          // placed marker coordinates match the file's native frame.
          setGeometry(geom);
          setError(null);
        } catch {
          setError("Failed to parse fork STL file");
        }
      });
  }, [stlBlob]);

  if (error) {
    return (
      <div
        style={{ padding: "24px", color: "red", textAlign: "center" }}
      >
        {error}
      </div>
    );
  }

  if (!geometry) {
    return (
      <div
        style={{
          width: "100%",
          height: "500px",
          background: "#1a1a2e",
          borderRadius: "8px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#6b7280",
        }}
      >
        Upload a fork STL to view it here
      </div>
    );
  }

  return (
    <div
      style={{
        width: "100%",
        height: "500px",
        background: "#1a1a2e",
        borderRadius: "8px",
      }}
    >
      <Canvas camera={{ position: [0, 50, 80], fov: 50 }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 10]} intensity={1} />
        <directionalLight position={[-10, -10, -5]} intensity={0.3} />

        <CameraFramer geometry={geometry} />

        <ForkMesh
          geometry={geometry}
          placingMode={placingMode}
          onTagPlaced={onTagPlaced}
          onHexPlaced={onHexPlaced}
        />

        <OriginAxes />

        {markers.map((m) => (
          <HexPostMarkerViz key={m.marker_id} marker={m} />
        ))}

        {placedTags.map((tag) => (
          <TagMarker key={tag.tag_id} tag={tag} />
        ))}

        <OrbitControls enableDamping dampingFactor={0.1} />
        <gridHelper args={[200, 40, "#444444", "#333333"]} />
      </Canvas>
    </div>
  );
}
