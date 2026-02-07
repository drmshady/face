/** STL 3D viewer using @react-three/fiber (T059). */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { STLExporter } from "three/examples/jsm/exporters/STLExporter.js";
import type { IntraOralMarker, Landmark3DInScan, Plane3D, TransformMatrix } from "../types";

interface StlViewerProps {
  stlUrl?: string;
  stlBlob?: Blob;
  markers?: IntraOralMarker[];
  planes?: Array<{ plane: Plane3D; color: string; label: string }>;
  forkStlBlob?: Blob;
  forkTransformMatrix?: TransformMatrix;
  landmarks3d?: Landmark3DInScan[];
  onExportFork?: (blob: Blob) => void;
}

function MeshFromGeometry({ geometry }: { geometry: THREE.BufferGeometry }) {
  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color="#b0b0b0" metalness={0.3} roughness={0.6} />
    </mesh>
  );
}

function TransformedForkMesh({
  blob,
  transformMatrix,
  meshRef,
}: {
  blob: Blob;
  transformMatrix?: TransformMatrix;
  meshRef: React.MutableRefObject<THREE.Mesh | null>;
}) {
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);

  useEffect(() => {
    const loader = new STLLoader();
    blob.arrayBuffer().then((buffer) => {
      try {
        const geom = loader.parse(buffer);
        geom.computeVertexNormals();
        setGeometry(geom);
      } catch {
        // silently ignore parse errors for fork mesh
      }
    });
  }, [blob]);

  const matrix = useMemo(() => {
    if (!transformMatrix) return undefined;
    const m = new THREE.Matrix4();
    // TransformMatrix.matrix is row-major 4x4
    const flat = transformMatrix.matrix.flat();
    m.fromArray(flat);
    m.transpose(); // three.js uses column-major
    return m;
  }, [transformMatrix]);

  if (!geometry) return null;

  return (
    <mesh
      ref={meshRef}
      geometry={geometry}
      matrixAutoUpdate={false}
      matrix={matrix}
    >
      <meshStandardMaterial
        color="#6d9eeb"
        metalness={0.2}
        roughness={0.7}
        transparent
        opacity={0.6}
      />
    </mesh>
  );
}

const LANDMARK_COLORS: Record<string, string> = {
  left_pupil: "#00ff00",
  right_pupil: "#00ff00",
  left_outer_canthus: "#00ccff",
  right_outer_canthus: "#00ccff",
  left_ala: "#ffcc00",
  right_ala: "#ffcc00",
  left_tragus: "#ff6600",
  right_tragus: "#ff6600",
  left_porion: "#ff00ff",
  right_porion: "#ff00ff",
  left_orbitale: "#ff3333",
  right_orbitale: "#ff3333",
};

function LandmarkSphere3D({ landmark }: { landmark: Landmark3DInScan }) {
  const color = LANDMARK_COLORS[landmark.name] ?? "#ffffff";
  return (
    <group position={[landmark.point.x, landmark.point.y, landmark.point.z]}>
      <mesh>
        <sphereGeometry args={[1.2, 12, 12]} />
        <meshStandardMaterial color={color} />
      </mesh>
      <Html distanceFactor={80} style={{ pointerEvents: "none" }}>
        <div
          style={{
            color: "white",
            fontSize: "10px",
            background: "rgba(0,0,0,0.6)",
            padding: "1px 4px",
            borderRadius: "3px",
            whiteSpace: "nowrap",
            transform: "translateX(-50%)",
          }}
        >
          {landmark.name.replace(/_/g, " ")}
        </div>
      </Html>
    </group>
  );
}

function MarkerSphere({ marker }: { marker: IntraOralMarker }) {
  return (
    <mesh position={[marker.position.x, marker.position.y, marker.position.z]}>
      <sphereGeometry args={[marker.fitted_radius, 16, 16]} />
      <meshStandardMaterial
        color={marker.confidence >= 0.8 ? "#22c55e" : marker.confidence >= 0.5 ? "#eab308" : "#ef4444"}
        transparent
        opacity={0.8}
      />
    </mesh>
  );
}

function PlaneOverlay({ plane, color }: { plane: Plane3D; color: string }) {
  const quaternion = useMemo(() => {
    const normal = new THREE.Vector3(plane.normal.x, plane.normal.y, plane.normal.z).normalize();
    const q = new THREE.Quaternion();
    q.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
    return q;
  }, [plane]);

  return (
    <mesh
      position={[plane.point.x, plane.point.y, plane.point.z]}
      quaternion={quaternion}
    >
      <planeGeometry args={[60, 60]} />
      <meshStandardMaterial color={color} transparent opacity={0.25} side={THREE.DoubleSide} />
    </mesh>
  );
}

export function StlViewer({
  stlUrl,
  stlBlob,
  markers = [],
  planes = [],
  forkStlBlob,
  forkTransformMatrix,
  landmarks3d = [],
  onExportFork,
}: StlViewerProps) {
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const forkMeshRef = useRef<THREE.Mesh | null>(null);

  useEffect(() => {
    const loader = new STLLoader();

    if (stlBlob) {
      stlBlob.arrayBuffer().then((buffer) => {
        try {
          const geom = loader.parse(buffer);
          geom.computeVertexNormals();
          setGeometry(geom);
        } catch {
          setError("Failed to parse STL file");
        }
      });
    } else if (stlUrl) {
      loader.load(
        stlUrl,
        (geom) => {
          geom.computeVertexNormals();
          setGeometry(geom);
        },
        undefined,
        () => setError("Failed to load STL file"),
      );
    }
  }, [stlUrl, stlBlob]);

  const handleExportFork = useCallback(() => {
    if (!forkMeshRef.current || !onExportFork) return;

    // Clone the mesh and apply the transform for export
    const mesh = forkMeshRef.current.clone();
    mesh.updateMatrixWorld(true);

    const exporter = new STLExporter();
    const result = exporter.parse(mesh, { binary: true });
    // binary mode returns DataView; convert to ArrayBuffer for Blob
    const buffer = result instanceof DataView ? result.buffer : result;
    const blob = new Blob([buffer as BlobPart], { type: "application/octet-stream" });
    onExportFork(blob);
  }, [onExportFork]);

  if (error) {
    return <div style={{ padding: "24px", color: "red", textAlign: "center" }}>{error}</div>;
  }

  return (
    <div>
      {/* Controls */}
      {(forkStlBlob || landmarks3d.length > 0) && (
        <div style={{ display: "flex", gap: "8px", marginBottom: "8px", alignItems: "center" }}>
          {forkStlBlob && (
            <span style={{ fontSize: "12px", color: "#6d9eeb" }}>
              Fork mesh shown (semi-transparent blue)
            </span>
          )}
          {landmarks3d.length > 0 && (
            <span style={{ fontSize: "12px", color: "#9ca3af" }}>
              {landmarks3d.length} landmarks in 3D
            </span>
          )}
          {forkStlBlob && onExportFork && (
            <button
              onClick={handleExportFork}
              style={{
                marginLeft: "auto",
                padding: "4px 12px",
                fontSize: "13px",
                border: "1px solid #2563eb",
                borderRadius: "4px",
                backgroundColor: "#eff6ff",
                color: "#2563eb",
                cursor: "pointer",
              }}
            >
              Export Aligned Fork STL
            </button>
          )}
        </div>
      )}

      <div style={{ width: "100%", height: "400px", background: "#1a1a2e", borderRadius: "8px" }}>
        <Canvas camera={{ position: [0, 0, 80], fov: 50 }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 10]} intensity={1} />
          <directionalLight position={[-10, -10, -5]} intensity={0.3} />

          {geometry && <MeshFromGeometry geometry={geometry} />}

          {forkStlBlob && (
            <TransformedForkMesh
              blob={forkStlBlob}
              transformMatrix={forkTransformMatrix}
              meshRef={forkMeshRef}
            />
          )}

          {markers.map((m) => (
            <MarkerSphere key={m.marker_id} marker={m} />
          ))}

          {landmarks3d.map((lm) => (
            <LandmarkSphere3D key={lm.name} landmark={lm} />
          ))}

          {planes.map((p, i) => (
            p.plane && <PlaneOverlay key={i} plane={p.plane} color={p.color} />
          ))}

          <OrbitControls enableDamping dampingFactor={0.1} />
        </Canvas>
      </div>
    </div>
  );
}
