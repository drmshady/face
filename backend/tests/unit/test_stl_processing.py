"""Unit tests for stl_processing service (T048)."""

import struct

import pytest


def _make_binary_stl(num_triangles: int = 4) -> bytes:
    """Create a valid binary STL with N triangles forming a simple shape."""
    header = b"\x00" * 80
    data = header + struct.pack("<I", num_triangles)
    for i in range(num_triangles):
        # normal
        data += struct.pack("<fff", 0, 0, 1)
        # 3 vertices at slightly different positions
        data += struct.pack("<fff", float(i), 0, 0)
        data += struct.pack("<fff", float(i + 1), 0, 0)
        data += struct.pack("<fff", float(i), 1, 0)
        # attribute byte count
        data += struct.pack("<H", 0)
    return data


class TestStlLoading:
    def test_load_stl_returns_metadata(self):
        """Loading a valid STL returns vertex count, face count, and bounding box."""
        from backend.src.services.stl_processing import load_stl

        stl_data = _make_binary_stl(4)
        result = load_stl(stl_data)

        assert result["vertex_count"] > 0
        assert result["face_count"] > 0
        assert "bounding_box" in result
        bb = result["bounding_box"]
        assert hasattr(bb, "min")
        assert hasattr(bb, "max")
        assert result["mesh"] is not None

    def test_load_stl_invalid_raises(self):
        """Loading invalid STL data raises an error."""
        from backend.src.services.stl_processing import load_stl

        with pytest.raises(Exception):
            load_stl(b"not valid stl data at all")


class TestMarkerDetection:
    def test_detect_markers_returns_marker_set(self):
        """Marker detection returns IntraOralMarkerSet structure."""
        from backend.src.services.stl_processing import detect_intra_oral_markers, load_stl

        stl_data = _make_binary_stl(4)
        result = load_stl(stl_data)
        mesh = result["mesh"]

        marker_set = detect_intra_oral_markers(mesh)
        # A simple flat mesh won't have sphere markers, so markers list should be empty
        assert marker_set is not None
        assert hasattr(marker_set, "markers")
        assert hasattr(marker_set, "markers_found")
        assert hasattr(marker_set, "sufficient")
        assert isinstance(marker_set.markers, list)

    def test_detect_markers_model_structure(self):
        """Verify IntraOralMarker model has required fields."""
        from backend.src.models.markers import IntraOralMarker
        from backend.src.models import Point3D

        marker = IntraOralMarker(
            marker_id=1,
            position=Point3D(x=10.0, y=-5.0, z=2.0),
            fitted_radius=1.5,
            confidence=0.95,
            residual=0.08,
        )
        assert marker.marker_id == 1
        assert marker.fitted_radius == 1.5
        assert marker.confidence == 0.95
        assert marker.residual == 0.08
