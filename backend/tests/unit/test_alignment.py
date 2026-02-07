"""Unit tests for alignment service (T049)."""

import numpy as np
import pytest


class TestCameraIntrinsics:
    def test_estimate_returns_3x3_matrix(self):
        """Camera intrinsics estimation returns a 3x3 matrix."""
        from backend.src.services.alignment import estimate_camera_intrinsics

        K = estimate_camera_intrinsics(1920, 1080)
        assert K.shape == (3, 3)
        # fx should be approximately image_width
        assert K[0, 0] > 0
        # Principal point should be near image center
        assert abs(K[0, 2] - 960) < 1
        assert abs(K[1, 2] - 540) < 1

    def test_estimate_with_focal_length(self):
        """Camera intrinsics with EXIF focal length uses it."""
        from backend.src.services.alignment import estimate_camera_intrinsics

        K = estimate_camera_intrinsics(1920, 1080, focal_length_mm=4.2)
        assert K.shape == (3, 3)
        assert K[0, 0] > 0


class TestSvdRegistration:
    def test_svd_registration_known_points(self):
        """SVD registration with known transform recovers rotation and translation."""
        from backend.src.services.alignment import solve_fork_to_scan_registration

        # Create known 3D points (fork frame)
        fork_pts = np.array([
            [0, 0, 0],
            [10, 0, 0],
            [0, 10, 0],
            [5, 5, 5],
        ], dtype=np.float64)

        # Known transform: translate by [1, 2, 3], no rotation
        known_t = np.array([1, 2, 3], dtype=np.float64)
        scan_pts = fork_pts + known_t

        R, t, rmsd = solve_fork_to_scan_registration(fork_pts, scan_pts)

        # R should be close to identity
        assert np.allclose(R, np.eye(3), atol=1e-6)
        # t should be [1, 2, 3]
        assert np.allclose(t, known_t, atol=1e-6)
        # RMSD should be near zero
        assert rmsd < 0.001

    def test_svd_registration_with_rotation(self):
        """SVD registration recovers rotation + translation."""
        from backend.src.services.alignment import solve_fork_to_scan_registration
        from scipy.spatial.transform import Rotation

        fork_pts = np.array([
            [0, 0, 0],
            [10, 0, 0],
            [0, 10, 0],
            [5, 5, 5],
        ], dtype=np.float64)

        # Known transform: 30 deg rotation about Z + translation
        R_known = Rotation.from_euler("z", 30, degrees=True).as_matrix()
        t_known = np.array([5, -3, 7], dtype=np.float64)
        scan_pts = (R_known @ fork_pts.T).T + t_known

        R_est, t_est, rmsd = solve_fork_to_scan_registration(fork_pts, scan_pts)

        assert np.allclose(R_est, R_known, atol=1e-6)
        assert np.allclose(t_est, t_known, atol=1e-6)
        assert rmsd < 0.001


class TestTransformComposition:
    def test_compose_t2_t1_inverse(self):
        """Composing T2 * T1^-1 produces correct combined matrix."""
        from backend.src.services.alignment import compose_alignment

        # T1: identity with translation [1, 0, 0]
        T1 = np.eye(4)
        T1[0, 3] = 1.0

        # T2: identity with translation [0, 2, 0]
        T2 = np.eye(4)
        T2[1, 3] = 2.0

        # T_face_to_scan = T2 * T1^-1
        # T1^-1 has translation [-1, 0, 0]
        # T2 * T1^-1 should give translation [-1, 2, 0]
        T_result = compose_alignment(T1, T2)

        assert T_result.shape == (4, 4)
        assert abs(T_result[0, 3] - (-1.0)) < 1e-6
        assert abs(T_result[1, 3] - 2.0) < 1e-6


class TestQualityClassification:
    def test_good_quality(self):
        """Good quality when reproj < 2px and RMSD < 0.3mm."""
        from backend.src.services.alignment import classify_quality

        assert classify_quality(1.0, 0.2) == "good"

    def test_acceptable_quality(self):
        """Acceptable quality when reproj < 5px and RMSD < 0.5mm."""
        from backend.src.services.alignment import classify_quality

        assert classify_quality(3.0, 0.4) == "acceptable"

    def test_poor_quality(self):
        """Poor quality when above acceptable thresholds."""
        from backend.src.services.alignment import classify_quality

        assert classify_quality(6.0, 0.6) == "poor"
