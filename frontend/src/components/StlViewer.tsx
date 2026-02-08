/** STL 3D viewer using @react-three/fiber (T059, T015-T019). */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { STLExporter } from "three/examples/jsm/exporters/STLExporter.js";
import type {
  AprilTagInFork,
  IntraOralMarker,
  Landmark3DInFork,
  Landmark3DInScan,
  Plane3D,
  ReferenceLine3D,
  ReferencePlane3D,
  TransformMatrix,
} from "../types";

interface StlViewerProps {
  stlUrl?: string;
  stlBlob?: Blob;
  markers?: IntraOralMarker[];
  planes?: Array<{ plane: Plane3D; color: string; label: string }>;
  forkStlBlob?: Blob;
  forkTransformMatrix?: TransformMatrix;
  landmarks3d?: Landmark3DInScan[];
  landmarks3dFork?: Landmark3DInFork[];
  apriltags?: AprilTagInFork[];
  interpupillaryLine?: ReferenceLine3D;
  midlinePlane?: ReferencePlane3D;
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

/** T015: Fork landmark sphere with depth confidence opacity */
function LandmarkSphere3DFork({ landmark }: { landmark: Landmark3DInFork }) {
  const color = LANDMARK_COLORS[landmark.name] ?? "#ffffff";
  const opacity = (landmark.depth_confidence ?? 0.5) > 0.8 ? 1.0
    : (landmark.depth_confidence ?? 0.5) > 0.5 ? 0.7 : 0.4;
  return (
    <group position={[landmark.point.x, landmark.point.y, landmark.point.z]}>
      <mesh>
        <sphereGeometry args={[1.2, 12, 12]} />
        <meshStandardMaterial color={color} transparent opacity={opacity} />
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

/** T015: AprilTag rectangle marker in 3D */
function AprilTagMarker3D({ tag }: { tag: AprilTagInFork }) {
  const quaternion = useMemo(() => {
    const normal = new THREE.Vector3(tag.normal.x, tag.normal.y, tag.normal.z).normalize();
    const q = new THREE.Quaternion();
    q.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
    return q;
  }, [tag]);

  return (
    <group position={[tag.center.x, tag.center.y, tag.center.z]} quaternion={quaternion}>
      <mesh>
        <planeGeometry args={[tag.size_mm, tag.size_mm]} />
        <meshStandardMaterial
          color="#f97316"
          transparent
          opacity={0.4}
          side={THREE.DoubleSide}
        />
      </mesh>
      <Html distanceFactor={100} style={{ pointerEvents: "none" }}>
        <div
          style={{
            color: "#f97316",
            fontSize: "9px",
            fontWeight: "bold",
            background: "rgba(0,0,0,0.5)",
            padding: "1px 4px",
            borderRadius: "3px",
            whiteSpace: "nowrap",
          }}
        >
          Tag {tag.tag_id}
        </div>
      </Html>
    </group>
  );
}

/** T016: Interpupillary reference line as tube */
function ReferenceLineTube({ line }: { line: ReferenceLine3D }) {
  const geometry = useMemo(() => {
    const start = new THREE.Vector3(line.start_point.x, line.start_point.y, line.start_point.z);
    const end = new THREE.Vector3(line.end_point.x, line.end_point.y, line.end_point.z);
    const path = new THREE.LineCurve3(start, end);
    return new THREE.TubeGeometry(path, 8, 0.8, 8, false);
  }, [line]);

  const midpoint = useMemo(() => {
    return new THREE.Vector3(
      (line.start_point.x + line.end_point.x) / 2,
      (line.start_point.y + line.end_point.y) / 2,
      (line.start_point.z + line.end_point.z) / 2,
    );
  }, [line]);

  return (
    <group>
      <mesh geometry={geometry}>
        <meshStandardMaterial color="#3b82f6" />
      </mesh>
      <Html position={[midpoint.x, midpoint.y + 3, midpoint.z]} distanceFactor={100} style={{ pointerEvents: "none" }}>
        <div
          style={{
            color: "#3b82f6",
            fontSize: "10px",
            fontWeight: "bold",
            background: "rgba(0,0,0,0.6)",
            padding: "2px 6px",
            borderRadius: "3px",
            whiteSpace: "nowrap",
          }}
        >
          IPD: {line.length_mm.toFixed(1)} mm
        </div>
      </Html>
    </group>
  );
}

/** T017: Midline plane overlay */
function ReferencePlane3DOverlay({ plane }: { plane: ReferencePlane3D }) {
  const quaternion = useMemo(() => {
    const normal = new THREE.Vector3(plane.normal.x, plane.normal.y, plane.normal.z).normalize();
    const q = new THREE.Quaternion();
    q.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
    return q;
  }, [plane]);

  return (
    <group position={[plane.point.x, plane.point.y, plane.point.z]} quaternion={quaternion}>
      <mesh>
        <planeGeometry args={[80, 80]} />
        <meshStandardMaterial
          color="#22c55e"
          transparent
          opacity={0.25}
          side={THREE.DoubleSide}
        />
      </mesh>
      <Html distanceFactor={120} style={{ pointerEvents: "none" }}>
        <div
          style={{
            color: "#22c55e",
            fontSize: "9px",
            fontWeight: "bold",
            background: "rgba(0,0,0,0.5)",
            padding: "1px 4px",
            borderRadius: "3px",
          }}
        >
          Midline
        </div>
      </Html>
    </group>
  );
}

/** T018: Dimension line between AprilTag centers */
function DimensionLine({ tags }: { tags: AprilTagInFork[] }) {
  if (tags.length < 2) return null;

  const start = tags[0].center;
  const end = tags[1].center;
  const distance = Math.sqrt(
    (end.x - start.x) ** 2 + (end.y - start.y) ** 2 + (end.z - start.z) ** 2,
  );

  const geometry = useMemo(() => {
    const s = new THREE.Vector3(start.x, start.y, start.z);
    const e = new THREE.Vector3(end.x, end.y, end.z);
    const path = new THREE.LineCurve3(s, e);
    return new THREE.TubeGeometry(path, 8, 0.4, 6, false);
  }, [start, end]);

  const mid = useMemo(() => new THREE.Vector3(
    (start.x + end.x) / 2,
    (start.y + end.y) / 2 - 3,
    (start.z + end.z) / 2,
  ), [start, end]);

  return (
    <group>
      <mesh geometry={geometry}>
        <meshStandardMaterial color="#a855f7" />
      </mesh>
      <Html position={[mid.x, mid.y, mid.z]} distanceFactor={100} style={{ pointerEvents: "none" }}>
        <div
          style={{
            color: "#a855f7",
            fontSize: "9px",
            fontWeight: "bold",
            background: "rgba(0,0,0,0.5)",
            padding: "1px 4px",
            borderRadius: "3px",
            whiteSpace: "nowrap",
          }}
        >
          {distance.toFixed(1)} mm
        </div>
      </Html>
    </group>
  );
}

/** T019: Main StlViewer with all new elements */
export function StlViewer({
  stlUrl,
  stlBlob,
  markers = [],
  planes = [],
  forkStlBlob,
  forkTransformMatrix,
  landmarks3d = [],
  landmarks3dFork = [],
  apriltags = [],
  interpupillaryLine,
  midlinePlane,
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

  const hasAnyContent = forkStlBlob || landmarks3d.length > 0 || landmarks3dFork.length > 0 || apriltags.length > 0;

  return (
    <div>
      {/* Controls */}
      {hasAnyContent && (
        <div style={{ display: "flex", gap: "8px", marginBottom: "8px", alignItems: "center", flexWrap: "wrap" }}>
          {forkStlBlob && (
            <span style={{ fontSize: "12px", color: "#6d9eeb" }}>
              Fork mesh shown (semi-transparent blue)
            </span>
          )}
          {landmarks3dFork.length > 0 && (
            <span style={{ fontSize: "12px", color: "#9ca3af" }}>
              {landmarks3dFork.length} landmarks in fork space
            </span>
          )}
          {apriltags.length > 0 && (
            <span style={{ fontSize: "12px", color: "#f97316" }}>
              {apriltags.length} AprilTags
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

          {/* Legacy scan-space landmarks */}
          {landmarks3d.map((lm) => (
            <LandmarkSphere3D key={lm.name} landmark={lm} />
          ))}

          {/* Fork-space landmarks with confidence opacity */}
          {landmarks3dFork.map((lm) => (
            <LandmarkSphere3DFork key={`fork-${lm.name}`} landmark={lm} />
          ))}

          {planes.map((p, i) => (
            p.plane && <PlaneOverlay key={i} plane={p.plane} color={p.color} />
          ))}

          {/* AprilTag markers */}
          {apriltags.map((tag) => (
            <AprilTagMarker3D key={`tag-${tag.tag_id}`} tag={tag} />
          ))}

          {/* Interpupillary line */}
          {interpupillaryLine && <ReferenceLineTube line={interpupillaryLine} />}

          {/* Midline plane */}
          {midlinePlane && <ReferencePlane3DOverlay plane={midlinePlane} />}

          {/* Dimension line between AprilTags */}
          {apriltags.length >= 2 && <DimensionLine tags={apriltags} />}

          <OrbitControls enableDamping dampingFactor={0.1} />
        </Canvas>
      </div>
    </div>
  );
}
