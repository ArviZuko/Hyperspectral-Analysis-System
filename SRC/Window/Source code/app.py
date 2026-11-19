"""
Hyperspectral Analysis System - single-file application.

This file is a straight, mechanical merge of the original modular project
(models/, controllers/, services/, ui/, main.py) into one file so the app
can be launched from a single .py file: `python spectrum_app.py`.
No algorithm, logic, or UI behavior was changed during the merge.
"""

from __future__ import annotations

import os
import enum
import sys
import io

import numpy as np
import cv2
import warnings
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PIL import Image
import pandas as pd
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QButtonGroup,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QApplication


def _app_base_dir() -> str:
    """Folder the app should treat as 'home' for user-visible files (Exports).

    - Running as a normal .py script: the script's folder.
    - Running as a PyInstaller --onefile .exe: the folder the .exe sits in
      (NOT the temporary _MEIxxxx extraction folder, which is deleted on exit).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bundled_resource_path(relative_path: str) -> str:
    """Folder for read-only bundled assets (weights, logo.png, logo.ico).

    - Running as a normal .py script: checks script directory and assets/ directory.
    - Running as a PyInstaller --onefile .exe: sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", _app_base_dir())
    direct_path = os.path.join(base, relative_path)
    if os.path.exists(direct_path):
        return direct_path
    asset_path = os.path.join(base, "assets", relative_path)
    if os.path.exists(asset_path):
        return asset_path
    return direct_path


# ============================================================================
# Spectrum model (weight loading, RGB -> spectrum transfer, spectral helpers)
# (originally: models/spectrum_model.py)
# ============================================================================

class SpectrumTransfer:

    def __init__(self):
        self.extend_mode = 0
        self.pca_eigenvectors = None
        self.pca_mean = None
        self.M = None
        self.TransM = None
        self.TransMin = 0.0
        self.TransMax = 1.0

    def get_extend_color(self, src_rgb):
        extend = None
        if self.extend_mode == 0:
            extend = np.array([
                src_rgb[:, 0], src_rgb[:, 1], src_rgb[:, 2],
                np.power(src_rgb[:, 0], 2),
                np.power(src_rgb[:, 1], 2),
                np.power(src_rgb[:, 2], 2)
            ])
        elif self.extend_mode == 1:
            extend = np.array([
                src_rgb[:, 0], src_rgb[:, 1], src_rgb[:, 2],
                np.power(src_rgb[:, 0], 2),
                np.power(src_rgb[:, 1], 2),
                np.power(src_rgb[:, 2], 2),
                src_rgb[:, 0] * src_rgb[:, 1],
                src_rgb[:, 0] * src_rgb[:, 2],
                src_rgb[:, 1] * src_rgb[:, 2]
            ])
        elif self.extend_mode == 2:
            extend = np.array([
                src_rgb[:, 0], src_rgb[:, 1], src_rgb[:, 2],
                np.power(src_rgb[:, 0], 2),
                np.power(src_rgb[:, 1], 2),
                np.power(src_rgb[:, 2], 2),
                src_rgb[:, 0] * src_rgb[:, 1],
                src_rgb[:, 0] * src_rgb[:, 2],
                src_rgb[:, 1] * src_rgb[:, 2],
                np.power(src_rgb[:, 0], 3),
                np.power(src_rgb[:, 1], 3),
                np.power(src_rgb[:, 2], 3)
            ])
        return extend

    def prepare(self):
        self.TransM = np.dot(self.M.T, self.pca_eigenvectors)

    def load_files(self, weights_path):
        self.M = np.load(os.path.join(weights_path, "a.npy"))
        self.pca_eigenvectors = np.load(os.path.join(weights_path, "b.npy"))
        self.pca_mean = np.load(os.path.join(weights_path, "c.npy"))
        d = np.load(os.path.join(weights_path, "d.npy"))
        self.TransMin = float(d[0])
        self.TransMax = float(d[1])
        e = np.load(os.path.join(weights_path, "e.npy"))
        self.extend_mode = int(e[0])
        self.prepare()

    def transfer(self, src_data):
        src_data = src_data.astype(np.float32)
        src_shape = src_data.shape

        if len(src_shape) >= 3:
            src_data = src_data.reshape(-1, src_shape[-1])

        tar_spec = np.dot(self.get_extend_color(src_data).T, self.TransM) + self.pca_mean

        if len(src_shape) >= 3:
            tar_spec = tar_spec.reshape(src_shape[0:-1] + (self.pca_mean.shape[0],))

        tar_spec = (tar_spec - self.TransMin) / (self.TransMax - self.TransMin)

        return tar_spec


# ── Spectral analysis helpers ────────────────────────────────────────────

def peak_wavelength(spectrum):
    """Find dominant wavelength (peak of spectrum)."""
    idx = np.argmax(spectrum)
    return float(380 + idx)


def spectral_energy(spectrum):
    """Calculate total spectral energy (integral approximation)."""
    # np.trapz was removed in NumPy 2.x in favor of np.trapezoid
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(spectrum, dx=1.0))
    return float(np.trapz(spectrum, dx=1.0))


def spectral_category(peak_nm):
    """Classify wavelength into color category."""
    if peak_nm < 380:
        return "UV"
    elif peak_nm < 450:
        return "Violet"
    elif peak_nm < 495:
        return "Blue"
    elif peak_nm < 570:
        return "Green"
    elif peak_nm < 590:
        return "Yellow"
    elif peak_nm < 620:
        return "Orange"
    elif peak_nm < 750:
        return "Red"
    else:
        return "IR"


def warmth_category(peak_nm):
    """Classify as warm or cool."""
    return "Warm" if peak_nm >= 570 else "Cool"


def spectral_distance(spec1, spec2):
    """Euclidean distance between two spectra."""
    return float(np.linalg.norm(spec1 - spec2))


def metameric_similarity(spec1, spec2):
    """
    Estimate metameric similarity (0-1, higher = more similar).
    Based on spectral correlation and RGB similarity.
    """
    # Normalize spectra
    spec1_norm = (spec1 - np.min(spec1)) / (np.max(spec1) - np.min(spec1) + 1e-8)
    spec2_norm = (spec2 - np.min(spec2)) / (np.max(spec2) - np.min(spec2) + 1e-8)
    
    # Correlation
    try:
        corr = np.corrcoef(spec1_norm, spec2_norm)[0, 1]
        corr = np.clip(corr, -1, 1)
    except:
        corr = 0.0
    
    # Convert correlation to similarity (0-1)
    similarity = (corr + 1) / 2
    return float(similarity)


def rgb_to_hsl(r, g, b):
    """Convert RGB (0-255) to HSL (0-360, 0-100, 0-100)."""
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0
    
    max_c = max(r_norm, g_norm, b_norm)
    min_c = min(r_norm, g_norm, b_norm)
    l = (max_c + min_c) / 2.0
    
    if max_c == min_c:
        h = s = 0.0
    else:
        d = max_c - min_c
        s = d / (2.0 - max_c - min_c) if l > 0.5 else d / (max_c + min_c)
        
        if max_c == r_norm:
            h = (g_norm - b_norm) / d + (6 if g_norm < b_norm else 0)
        elif max_c == g_norm:
            h = (b_norm - r_norm) / d + 2
        else:
            h = (r_norm - g_norm) / d + 4
        h /= 6.0
    
    return (
        int(h * 360),
        int(s * 100),
        int(l * 100)
    )


def color_temp_kelvin(r, g, b):
    """Rough CCT estimate via McCamy's formula on chromaticity."""
    if r + g + b == 0:
        return 0
    xc = r / (r + g + b)
    yc = g / (r + g + b)
    if yc == 0:
        return 0
    n = (xc - 0.3320) / (0.1858 - yc)
    cct = 449 * (n ** 3) + 3525 * (n ** 2) + 6823.3 * n + 5520.33
    return max(1000, min(20000, int(cct)))


# ============================================================================
# Annotation model (ROI tool state + mask generation)
# (originally: models/annotation_model.py)
# ============================================================================

class AnnotationTool(enum.Enum):
    NONE = "none"
    POINT = "point"
    RECT = "rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    POLYGON = "polygon"


class AnnotationManager:
    def __init__(self):
        self.tool = AnnotationTool.POINT
        self.points: list[tuple[int, int]] = []
        self.drawing = False

    def set_tool(self, tool: AnnotationTool) -> None:
        self.tool = tool
        self.clear()

    def clear(self) -> None:
        self.points.clear()
        self.drawing = False

    def generate_mask(self, grid_h: int, grid_w: int) -> np.ndarray | None:
        """
        Generates a boolean mask of shape (grid_h, grid_w) based on the current points and tool.
        """
        if not self.points or grid_h <= 0 or grid_w <= 0:
            return None

        mask = np.zeros((grid_h, grid_w), dtype=bool)

        if self.tool == AnnotationTool.POINT:
            # Single pixel block selection
            x, y = self.points[-1]
            x = max(0, min(x, grid_w - 1))
            y = max(0, min(y, grid_h - 1))
            mask[y, x] = True
            return mask

        elif self.tool == AnnotationTool.RECT:
            if len(self.points) < 2:
                return None
            x1, y1 = self.points[0]
            x2, y2 = self.points[1]
            x0, x3 = sorted((x1, x2))
            y0, y3 = sorted((y1, y2))
            x0 = max(0, min(x0, grid_w - 1))
            x3 = max(0, min(x3, grid_w - 1))
            y0 = max(0, min(y0, grid_h - 1))
            y3 = max(0, min(y3, grid_h - 1))
            mask[y0 : y3 + 1, x0 : x3 + 1] = True
            return mask

        elif self.tool == AnnotationTool.ELLIPSE:
            if len(self.points) < 2:
                return None
            x1, y1 = self.points[0]
            x2, y2 = self.points[1]
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            rx = max(abs(x2 - x1) / 2.0, 0.5)
            ry = max(abs(y2 - y1) / 2.0, 0.5)
            ys, xs = np.ogrid[:grid_h, :grid_w]
            inside = ((xs - cx) ** 2) / (rx ** 2) + ((ys - cy) ** 2) / (ry ** 2) <= 1.0
            mask[inside] = True
            return mask

        elif self.tool == AnnotationTool.LINE:
            if len(self.points) < 2:
                return None
            x1, y1 = self.points[0]
            x2, y2 = self.points[1]
            line_pts = self._bresenham_line(x1, y1, x2, y2)
            for x, y in line_pts:
                if 0 <= x < grid_w and 0 <= y < grid_h:
                    mask[y, x] = True
            return mask

        elif self.tool == AnnotationTool.POLYGON:
            if len(self.points) < 3:
                return None
            poly_mask = np.zeros((grid_h, grid_w), dtype=np.uint8)
            pts = np.array(self.points, dtype=np.int32)
            cv2.fillPoly(poly_mask, [pts], 1)
            return poly_mask.astype(bool)

        return None

    @staticmethod
    def _bresenham_line(x1: int, y1: int, x2: int, y2: int) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        x, y = x1, y1
        while True:
            points.append((x, y))
            if x == x2 and y == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
        return points


# ============================================================================
# Camera manager (live camera capture via OpenCV / Picamera2 / GStreamer)
# (originally: controllers/camera_manager.py)
# ============================================================================

class UniversalVideoCapture:
    @staticmethod
    def get_available_cameras(max_tested: int = 6) -> list[int]:
        """
        Scans camera device indices from 0 up to max_tested-1 safely.
        Returns a list of available camera device indices.
        """
        available = []
        for idx in range(max_tested):
            try:
                cap = None
                if sys.platform.startswith("win"):
                    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
                        try:
                            temp_cap = cv2.VideoCapture(idx, backend)
                            if temp_cap.isOpened():
                                cap = temp_cap
                                break
                            else:
                                temp_cap.release()
                        except Exception:
                            pass
                else:
                    temp_cap = cv2.VideoCapture(idx)
                    if temp_cap.isOpened():
                        cap = temp_cap

                if cap is not None and cap.isOpened():
                    ok, frame = cap.read()
                    cap.release()
                    if ok and frame is not None and frame.size > 0:
                        available.append(idx)
            except Exception:
                pass
        return available if available else [0]

    def __init__(self, device_index: int = 0):
        self.device_index = device_index
        self.cap = None
        self.picam = None
        self._is_picam = False

        # 1. Try standard picamera2 if we are on Linux/Raspberry Pi
        if not sys.platform.startswith("win"):
            try:
                from picamera2 import Picamera2
                # Initialize picamera2
                self.picam = Picamera2()
                config = self.picam.create_preview_configuration({"format": "RGB888", "size": (640, 480)})
                self.picam.configure(config)
                self.picam.start()
                self._is_picam = True
                return
            except Exception:
                if self.picam is not None:
                    try:
                        self.picam.stop()
                        self.picam.close()
                    except Exception:
                        pass
                    self.picam = None
                self._is_picam = False

        # 2. Try GStreamer pipeline with libcamerasrc if on Linux
        if not sys.platform.startswith("win"):
            gst_pipeline = (
                "libcamerasrc ! "
                "video/x-raw, width=640, height=480, framerate=30/1 ! "
                "videoconvert ! video/x-raw, format=BGR ! "
                "appsink max-buffers=1 drop=True"
            )
            try:
                self.cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                if self.cap.isOpened():
                    # Test if we can read a frame
                    ok, frame = self.cap.read()
                    if ok and frame is not None and frame.size > 0:
                        return
                    else:
                        self.cap.release()
                        self.cap = None
            except Exception:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None

        # 3. Try standard V4L2 on Linux
        if not sys.platform.startswith("win"):
            try:
                self.cap = cv2.VideoCapture(device_index, cv2.CAP_V4L2)
                if self.cap.isOpened():
                    # Try setting MJPG format which is standard for RPi V4L2 compat layer
                    self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    
                    # Test read
                    ok, frame = self.cap.read()
                    if ok and frame is not None and frame.size > 0:
                        return
                    else:
                        self.cap.release()
                        self.cap = None
            except Exception:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None

        # 4. Multi-backend attempt for Windows and standard platforms
        if sys.platform.startswith("win"):
            backends = []
            if hasattr(cv2, "CAP_DSHOW"):
                backends.append(cv2.CAP_DSHOW)
            if hasattr(cv2, "CAP_MSMF"):
                backends.append(cv2.CAP_MSMF)
            backends.append(cv2.CAP_ANY)
        else:
            backends = [cv2.CAP_ANY]

        for b in backends:
            try:
                cap = cv2.VideoCapture(device_index, b)
                if cap.isOpened():
                    ok, frame = cap.read()
                    if ok and frame is not None and frame.size > 0:
                        self.cap = cap
                        return
                    else:
                        cap.release()
            except Exception:
                pass

        # Final fallback attempt
        try:
            self.cap = cv2.VideoCapture(device_index)
        except Exception:
            self.cap = None

    def isOpened(self) -> bool:
        if self._is_picam:
            return self.picam is not None
        return self.cap is not None and self.cap.isOpened()

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._is_picam:
            try:
                frame = self.picam.capture_array("main")
                if frame is not None:
                    if len(frame.shape) == 3 and frame.shape[2] == 4:
                        frame = frame[:, :, :3]
                    return True, frame
            except Exception:
                return False, None
        if self.cap is not None:
            try:
                ok, frame = self.cap.read()
                if ok and frame is not None and isinstance(frame, np.ndarray) and frame.size > 0:
                    return True, frame
            except Exception:
                pass
        return False, None

    def release(self) -> None:
        if self._is_picam:
            if self.picam is not None:
                try:
                    self.picam.stop()
                    self.picam.close()
                except Exception:
                    pass
                self.picam = None
        elif self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def set(self, prop, value) -> bool:
        if self._is_picam:
            return True
        if self.cap is not None:
            try:
                return self.cap.set(prop, value)
            except Exception:
                pass
        return False


class CameraManager(QObject):
    frame_ready = pyqtSignal(np.ndarray)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._capture: UniversalVideoCapture | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._read_frame)
        self._last_frame: np.ndarray | None = None
        self._consecutive_failures = 0

    def start_camera(self, device_index: int = 0) -> bool:
        self.stop_camera()
        self._capture = UniversalVideoCapture(device_index)

        if not self._capture.isOpened():
            self._capture = None
            return False

        if not sys.platform.startswith("win"):
            # Try to negotiate preferred format/resolution if using OpenCV backend
            self._capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self._consecutive_failures = 0
        self._timer.start(33)  # ~30 FPS
        return True

    def stop_camera(self) -> None:
        self._timer.stop()
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._last_frame = None
        self._consecutive_failures = 0

    def is_active(self) -> bool:
        return self._capture is not None and self._timer.isActive()

    def _read_frame(self) -> None:
        if self._capture is None:
            return
        try:
            ok, frame = self._capture.read()
            if not ok or frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
                self._consecutive_failures += 1
                if self._consecutive_failures == 30:  # ~1 second of failed reads at 30 FPS
                    warnings.warn(
                        "Camera opened but is not returning frames. Check that no other "
                        "process is using the camera, and that the required pixel format "
                        "is supported by the device.",
                        RuntimeWarning,
                    )
                return
            self._consecutive_failures = 0
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._last_frame = rgb_frame.copy()
            self.frame_ready.emit(rgb_frame)
        except Exception as exc:
            self._consecutive_failures += 1
            if self._consecutive_failures == 30:
                warnings.warn(f"Exception during frame capture: {exc}", RuntimeWarning)

    def capture_frame(self) -> np.ndarray | None:
        """Returns the last read camera frame as an RGB numpy array."""
        if self._last_frame is not None:
            return self._last_frame.copy()
        if self._capture is not None:
            try:
                ok, frame = self._capture.read()
                if ok and frame is not None and isinstance(frame, np.ndarray) and frame.size > 0:
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception:
                pass
        return None


# ============================================================================
# Spectrum analyzer (image -> spectral cube pipeline)
# (originally: controllers/spectrum_analyzer.py)
# ============================================================================

class SpectrumAnalyzer:
    def __init__(self, weights_path: str | None = None):
        self.weights_path = weights_path or _bundled_resource_path("weights")
        self.transfer = SpectrumTransfer()
        self._model_loaded = False

    def ensure_model(self) -> None:
        if self._model_loaded:
            return
        if not os.path.isdir(self.weights_path):
            raise FileNotFoundError(
                f"Model weights not found at {self.weights_path}. "
                "Place a.npy through e.npy in the weights folder."
            )
        self.transfer.load_files(self.weights_path)
        self._model_loaded = True

    def process_image(self, img: Image.Image, block_size: int = 8) -> tuple[np.ndarray, np.ndarray]:
        """
        Process the image, returning (spectrum_array, block_image_array).
        - spectrum_array: (H, W, 401) reconstructed spectra
        - block_image_array: (H, W, 3) downsampled RGB image
        """
        self.ensure_model()
        img = img.convert("RGB")

        # Calculate grid size based on block_size
        grid_w = img.width // block_size
        grid_h = img.height // block_size
        if grid_w < 1 or grid_h < 1:
            raise ValueError("Image is too small for the selected block size.")

        # Crop to grid multiple
        img = img.crop((0, 0, grid_w * block_size, grid_h * block_size))
        img_np = np.array(img, dtype=np.uint8)

        # Average colors inside block size
        block_img = (
            img_np.reshape(grid_h, block_size, grid_w, block_size, 3)
            .mean(axis=(1, 3))
            .astype(np.uint8)
        )

        # Predict spectral cube
        spec_array = self.transfer.transfer(block_img).astype(np.float32)
        return spec_array, block_img

    def get_roi_spectrum(self, spectrum_array: np.ndarray | None, mask: np.ndarray | None) -> np.ndarray | None:
        """
        Calculates the average spectrum for the given binary mask.
        - spectrum_array: (H, W, 401)
        - mask: (H, W) boolean mask
        Returns average spectrum array of shape (401,) or None.
        """
        if spectrum_array is None or mask is None:
            return None

        sh, sw = spectrum_array.shape[:2]
        if mask.shape[0] != sh or mask.shape[1] != sw:
            import cv2
            mask = cv2.resize(mask.astype(np.uint8), (sw, sh), interpolation=cv2.INTER_NEAREST).astype(bool)

        indices = np.argwhere(mask)
        if len(indices) == 0:
            return None

        ys, xs = indices[:, 0], indices[:, 1]
        return spectrum_array[ys, xs].mean(axis=0)


# ============================================================================
# Export service (CSV / Excel export of ROI spectra)
# (originally: services/export_service.py)
# ============================================================================

SPEC_START = 380
SPEC_END = 780
WAVELENGTHS = list(range(SPEC_START, SPEC_END + 1))  # 401 values


def build_roi_csv_df(roi_list: list[dict], spectrum_array: np.ndarray, analyzer) -> pd.DataFrame:
    """
    Builds the DataFrame for the ROI data export (CSV).
    Contains only active ROI annotations of supported types.
    """
    supported_types = {"Rectangle", "Ellipse", "Point", "Polygon"}
    rows = []
    
    for idx, roi in enumerate(roi_list):
        label = roi.get("label", "")
        roi_type = label.split()[0] if label else "Unknown"
        
        # Ensure it is a supported ROI type
        if roi_type not in supported_types:
            continue
            
        avg_spectrum = analyzer.get_roi_spectrum(spectrum_array, roi["mask"])
        if avg_spectrum is None:
            continue

        roi_id = idx + 1

        for i, wl in enumerate(WAVELENGTHS):
            intensity_val = float(avg_spectrum[i])
            rows.append({
                "ROI ID": f"ROI {roi_id}",
                "Wavelength": f"{wl}nm",
                "Intensity": round(intensity_val, 5)
            })

    return pd.DataFrame(rows)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def to_excel_bytes_roi(roi_list: list[dict], spectrum_array: np.ndarray, analyzer) -> bytes:
    """
    Generates Excel bytes with 4 separate sheets:
    1. Rectangle ROI
    2. Ellipse ROI
    3. Point ROI
    4. Polygon ROI
    Each sheet contains ROI_ID, Wavelength, and Intensity.
    """
    supported_types = ["Rectangle", "Ellipse", "Point", "Polygon"]
    sheet_names = {
        "Rectangle": "Rectangle ROI",
        "Ellipse": "Ellipse ROI",
        "Point": "Point ROI",
        "Polygon": "Polygon ROI"
    }
    
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for roi_type in supported_types:
            sheet_name = sheet_names[roi_type]
            sheet_rows = []
            
            for idx, roi in enumerate(roi_list):
                label = roi.get("label", "")
                curr_type = label.split()[0] if label else "Unknown"
                if curr_type != roi_type:
                    continue
                    
                avg_spectrum = analyzer.get_roi_spectrum(spectrum_array, roi["mask"])
                if avg_spectrum is None:
                    continue
                    
                roi_id = idx + 1
                for i, wl in enumerate(WAVELENGTHS):
                    intensity_val = float(avg_spectrum[i])
                    sheet_rows.append({
                        "ROI_ID": roi_id,
                        "Wavelength": f"{wl}nm",
                        "Intensity": round(intensity_val, 5)
                    })
            
            if sheet_rows:
                df_sheet = pd.DataFrame(sheet_rows)
            else:
                df_sheet = pd.DataFrame(columns=["ROI_ID", "Wavelength", "Intensity"])
                
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
            
    buf.seek(0)
    return buf.read()


# ============================================================================
# UI stylesheet (dark theme)
# (originally: ui/styles.py)
# ============================================================================

WINDOWS_THEME = """
QMainWindow, QWidget {
    background-color: #f3f3f3;
    color: #201f1e;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QPushButton {
    background-color: #ffffff;
    border: 1px solid #adadad;
    border-radius: 4px;
    padding: 8px 14px;
    color: #201f1e;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #f3f3f3;
    border-color: #8a8886;
}

QPushButton:pressed {
    background-color: #e1e1e1;
    border-color: #605e5c;
}

QPushButton:disabled {
    background-color: #f3f3f3;
    color: #a19f9d;
    border-color: #d1d1d1;
}

QPushButton#primary {
    background-color: #0078d4;
    border-color: #005a9e;
    color: #ffffff;
}

QPushButton#primary:hover {
    background-color: #106ebe;
}

QPushButton#primary:pressed {
    background-color: #005a9e;
}

QPushButton#secondary {
    background-color: #ffffff;
    border: 1px solid #adadad;
    color: #201f1e;
}

QPushButton#secondary:hover {
    background-color: #f3f3f3;
    border-color: #8a8886;
}

QPushButton#secondary:pressed {
    background-color: #e1e1e1;
}

QPushButton#danger {
    background-color: #ffffff;
    border: 1px solid #c42b1c;
    color: #c42b1c;
}

QPushButton#danger:hover {
    background-color: #fde7e9;
    border-color: #a4262c;
}

QPushButton#danger:pressed {
    background-color: #fad4d8;
}

QLineEdit {
    background-color: #ffffff;
    border: 1px solid #adadad;
    border-radius: 4px;
    padding: 5px 8px;
    color: #201f1e;
}

QLineEdit:focus {
    border-color: #0078d4;
}

QStatusBar {
    background-color: #f3f3f3;
    color: #605e5c;
    border-top: 1px solid #d1d1d1;
}

QFrame#panel {
    background-color: #ffffff;
    border: 1px solid #d1d1d1;
    border-radius: 6px;
}

QFrame#canvasFrame {
    background-color: #ffffff;
    border: 1px solid #d1d1d1;
    border-radius: 6px;
}

QProgressBar {
    border: none;
    border-radius: 4px;
    background: #e1e1e1;
    text-align: center;
    color: #201f1e;
    max-height: 8px;
}

QProgressBar::chunk {
    background: #0078d4;
    border-radius: 4px;
}
"""


# ============================================================================
# Image display widget (canvas, ROI drawing, annotations)
# (originally: ui/image_display_widget.py)
# ============================================================================

class ImageDisplayWidget(QGraphicsView):
    roi_list_changed = pyqtSignal(list)  # Emits the list of active ROIs

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("canvas")
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(QBrush(QColor("#e5e5e5")))

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._grid_w = 0
        self._grid_h = 0
        self._scale = 1.0
        self._zoom_level = 1.0
        self._min_zoom = 1.0
        self._max_zoom = 8.0
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        self._annotation_manager = AnnotationManager()
        self._temp_item = None
        self._drawing_items: list = []

        self.roi_list: list[dict] = []
        self._roi_counter: dict[AnnotationTool, int] = {t: 0 for t in AnnotationTool}
        self._color_palette = [
            "#3b82f6", "#f97316", "#22c55e", "#a855f7", "#ef4444",
            "#14b8a6", "#eab308", "#ec4899", "#06b6d4", "#84cc16"
        ]

        self._build_toolbar()

    def _build_toolbar(self) -> None:
        self._toolbar = QFrame(self)
        self._toolbar.setObjectName("floatingToolbar")
        self._toolbar.setStyleSheet("""
            QFrame#floatingToolbar {
                background-color: rgba(255, 255, 255, 0.92);
                border: 1px solid #d1d1d1;
                border-radius: 6px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                color: #605e5c;
                font-weight: 500;
                font-size: 11px;
                min-width: 50px;
                min-height: 16px;
            }
            QPushButton:hover {
                background-color: rgba(225, 225, 225, 0.85);
                color: #201f1e;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: #ffffff;
            }
        """)

        layout = QHBoxLayout(self._toolbar)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        tools = [
            (AnnotationTool.POINT, "Point"),
            (AnnotationTool.RECT, "Rect"),
            (AnnotationTool.ELLIPSE, "Ellipse"),
        ]

        self._buttons: dict[AnnotationTool, QPushButton] = {}
        for tool, label in tools:
            btn = QPushButton(label)
            btn.setCheckable(True)
            if tool == AnnotationTool.POINT:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, t=tool: self._select_tool(t))
            layout.addWidget(btn)
            self._btn_group.addButton(btn)
            self._buttons[tool] = btn

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet("color: #d1d1d1;")
        layout.addWidget(separator)

        self._btn_zoom_out = QPushButton("Zoom Out")
        self._btn_zoom_out.setToolTip("Zoom Out")
        self._btn_zoom_out.clicked.connect(self.zoom_out)
        layout.addWidget(self._btn_zoom_out)

        self._btn_zoom_in = QPushButton("Zoom In")
        self._btn_zoom_in.setToolTip("Zoom In")
        self._btn_zoom_in.clicked.connect(self.zoom_in)
        layout.addWidget(self._btn_zoom_in)

        self._toolbar.adjustSize()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_toolbar"):
            margin = 10
            self._toolbar.move(
                self.width() - self._toolbar.width() - margin,
                margin
            )
        if self._pixmap_item is not None:
            self._apply_zoom()

    def _select_tool(self, tool: AnnotationTool) -> None:
        self._annotation_manager.set_tool(tool)
        # We don't clear all annotations on tool switch, only active/drawing annotations
        if self._temp_item is not None:
            try:
                self._scene.removeItem(self._temp_item)
            except:
                pass
            self._temp_item = None

    def set_image(self, image_array: np.ndarray, original_image: np.ndarray | None = None) -> None:
        """Sets the processed/block static image."""
        self.clear_all()

        self._grid_h, self._grid_w = image_array.shape[:2]

        # Display original high-resolution image if available, else block image
        display_array = original_image if original_image is not None else image_array
        h, w, _ = display_array.shape
        qimg = QImage(display_array.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg)

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._zoom_level = 1.0
        self._apply_zoom()
        self._scale = self.transform().m11()

        self._toolbar.setEnabled(True)
        self._select_tool(self._annotation_manager.tool)

    def set_camera_frame(self, frame_array: np.ndarray) -> None:
        """Sets the active camera stream frame."""
        self.clear_annotations()
        self._toolbar.setEnabled(False)

        h, w, _ = frame_array.shape
        qimg = QImage(frame_array.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimg)

        if self._pixmap_item is None:
            self._scene.clear()
            self._pixmap_item = self._scene.addPixmap(pixmap)
            self._scene.setSceneRect(QRectF(pixmap.rect()))
            self._zoom_level = 1.0
            self._apply_zoom()
        else:
            self._pixmap_item.setPixmap(pixmap)

    def clear_annotations(self) -> None:
        """Clears active ROI lines and shapes from screen."""
        self._annotation_manager.clear()
        if self._temp_item is not None:
            try:
                self._scene.removeItem(self._temp_item)
            except:
                pass
            self._temp_item = None

        for item in self._drawing_items:
            try:
                self._scene.removeItem(item)
            except:
                pass
        self._drawing_items.clear()
        self.roi_list.clear()
        for t in self._roi_counter:
            self._roi_counter[t] = 0

        self.roi_list_changed.emit(self.roi_list)

    def clear_all(self) -> None:
        """Resets the canvas completely."""
        self.clear_annotations()
        self._scene.clear()
        self._pixmap_item = None
        self._grid_w = 0
        self._grid_h = 0

    def wheelEvent(self, event) -> None:
        if self._pixmap_item is None:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._set_zoom(self._zoom_level * factor)
        event.accept()

    def _apply_zoom(self) -> None:
        """Re-fits the image to the viewport, then applies the current zoom multiplier on top."""
        if self._pixmap_item is None:
            return
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        if self._zoom_level != 1.0:
            self.scale(self._zoom_level, self._zoom_level)

    def _set_zoom(self, new_zoom: float) -> None:
        if self._pixmap_item is None:
            return
        new_zoom = max(self._min_zoom, min(self._max_zoom, new_zoom))
        if new_zoom == self._zoom_level:
            return
        self._zoom_level = new_zoom
        self._apply_zoom()

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom_level * 1.25)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom_level / 1.25)

    def _scene_to_grid(self, pos: QPointF) -> tuple[int, int] | None:
        if self._pixmap_item is None or self._grid_w == 0:
            return None
        local = self._pixmap_item.mapFromScene(pos)
        
        # Calculate scale factor between displayed image size and block grid size
        pixmap_rect = self._pixmap_item.pixmap().rect()
        scale_x = pixmap_rect.width() / self._grid_w
        scale_y = pixmap_rect.height() / self._grid_h
        
        grid_x = int(local.x() / scale_x)
        grid_y = int(local.y() / scale_y)
        
        if grid_x < 0 or grid_y < 0 or grid_x >= self._grid_w or grid_y >= self._grid_h:
            return None
        return grid_x, grid_y

    def _grid_to_scene(self, grid_x: int, grid_y: int) -> QPointF:
        if self._pixmap_item is None or self._grid_w == 0:
            return QPointF(grid_x, grid_y)
            
        pixmap_rect = self._pixmap_item.pixmap().rect()
        scale_x = pixmap_rect.width() / self._grid_w
        scale_y = pixmap_rect.height() / self._grid_h
        
        scene_x = grid_x * scale_x
        scene_y = grid_y * scale_y
        return QPointF(scene_x, scene_y)

    def _make_pen(self, color: str = "#38bdf8", width: float = 1.0) -> QPen:
        pen = QPen(QColor(color))
        pen.setWidthF(width)
        pen.setCosmetic(True)  # Keeps pen thickness constant on screen (thin and clean)
        return pen

    def _make_brush(self, color: str = "#38bdf8", alpha: int = 40) -> QBrush:
        qcolor = QColor(color)
        qcolor.setAlpha(alpha)
        return QBrush(qcolor)

    def _add_roi_number_label(self, number: int, x: float, y: float) -> None:
        """Draws a small numeric label near an ROI (matches the ROI ID used in CSV/Excel export)."""
        text_item = QGraphicsSimpleTextItem(str(number))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(QColor("#ffffff")))
        text_item.setPen(QPen(QColor("#000000"), 0.6))
        text_item.setPos(x, y)
        text_item.setZValue(20)
        self._scene.addItem(text_item)
        self._drawing_items.append(text_item)

    def _tool_label(self, tool: AnnotationTool) -> str:
        if tool == AnnotationTool.RECT:
            return "Rectangle"
        elif tool == AnnotationTool.ELLIPSE:
            return "Ellipse"
        elif tool == AnnotationTool.LINE:
            return "Line"
        elif tool == AnnotationTool.POINT:
            return "Point"
        return "ROI"

    def mousePressEvent(self, event) -> None:
        if self._pixmap_item is None or not self._toolbar.isEnabled():
            super().mousePressEvent(event)
            return

        pos = self.mapToScene(event.position().toPoint())
        grid = self._scene_to_grid(pos)
        if grid is None:
            return

        tool = self._annotation_manager.tool

        pixmap_rect = self._pixmap_item.pixmap().rect()
        scale_x = pixmap_rect.width() / self._grid_w
        scale_y = pixmap_rect.height() / self._grid_h

        if tool == AnnotationTool.POINT:
            x, y = grid
            self._annotation_manager.points = [grid]

            self._roi_counter[AnnotationTool.POINT] += 1
            label = f"Point {self._roi_counter[AnnotationTool.POINT]}"
            color = self._color_palette[len(self.roi_list) % len(self._color_palette)]

            # Draw permanent point marker centered in the block
            pt = self._grid_to_scene(x, y)
            cx = pt.x() + scale_x / 2
            cy = pt.y() + scale_y / 2
            marker_w = max(4.0, scale_x * 0.3)
            marker_h = max(4.0, scale_y * 0.3)
            rect = QRectF(cx - marker_w / 2, cy - marker_h / 2, marker_w, marker_h)
            item = self._scene.addEllipse(rect, self._make_pen(color, 1.0), self._make_brush(color, 255))
            item.setZValue(10)
            self._drawing_items.append(item)

            roi_number = self._roi_counter[AnnotationTool.POINT]
            self._add_roi_number_label(roi_number, cx + marker_w / 2 + 2, cy - marker_h / 2 - 12)

            mask = self._annotation_manager.generate_mask(self._grid_h, self._grid_w)
            if mask is not None:
                self.roi_list.append({
                    "label": label,
                    "mask": mask,
                    "color": color
                })
                self.roi_list_changed.emit(self.roi_list)
            return

        # Rect, Ellipse, Line drag-draw
        self._annotation_manager.drawing = True
        self._annotation_manager.points = [grid]

        sx, sy = grid
        p_scene = self._grid_to_scene(sx, sy)
        if tool == AnnotationTool.RECT:
            self._temp_item = QGraphicsRectItem(QRectF(p_scene.x(), p_scene.y(), scale_x, scale_y))
            self._temp_item.setBrush(self._make_brush("#38bdf8", 40))
        elif tool == AnnotationTool.ELLIPSE:
            self._temp_item = QGraphicsEllipseItem(QRectF(p_scene.x(), p_scene.y(), scale_x, scale_y))
            self._temp_item.setBrush(self._make_brush("#38bdf8", 40))
        elif tool == AnnotationTool.LINE:
            self._temp_item = QGraphicsLineItem(p_scene.x() + scale_x / 2, p_scene.y() + scale_y / 2, p_scene.x() + scale_x / 2, p_scene.y() + scale_y / 2)

        if self._temp_item is not None:
            self._temp_item.setPen(self._make_pen("#38bdf8", 1.0))
            self._temp_item.setZValue(5)
            self._scene.addItem(self._temp_item)

    def mouseMoveEvent(self, event) -> None:
        tool = self._annotation_manager.tool

        if not self._annotation_manager.drawing or not self._annotation_manager.points or self._temp_item is None:
            super().mouseMoveEvent(event)
            return

        pos = self.mapToScene(event.position().toPoint())
        grid = self._scene_to_grid(pos)
        if grid is None:
            return

        sx, sy = self._annotation_manager.points[0]
        ex, ey = grid

        pixmap_rect = self._pixmap_item.pixmap().rect()
        scale_x = pixmap_rect.width() / self._grid_w
        scale_y = pixmap_rect.height() / self._grid_h

        p1 = self._grid_to_scene(sx, sy)
        p2 = self._grid_to_scene(ex, ey)
        x0 = min(p1.x(), p2.x())
        y0 = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x()) + scale_x
        h = abs(p2.y() - p1.y()) + scale_y

        if tool == AnnotationTool.RECT:
            self._temp_item.setRect(QRectF(x0, y0, w, h))
        elif tool == AnnotationTool.ELLIPSE:
            self._temp_item.setRect(QRectF(x0, y0, w, h))
        elif tool == AnnotationTool.LINE:
            self._temp_item.setLine(p1.x() + scale_x / 2, p1.y() + scale_y / 2, p2.x() + scale_x / 2, p2.y() + scale_y / 2)

    def mouseReleaseEvent(self, event) -> None:
        tool = self._annotation_manager.tool
        if not self._annotation_manager.drawing or not self._annotation_manager.points:
            super().mouseReleaseEvent(event)
            return

        self._annotation_manager.drawing = False
        pos = self.mapToScene(event.position().toPoint())
        grid = self._scene_to_grid(pos)
        if grid is None:
            grid = self._annotation_manager.points[0]

        self._annotation_manager.points.append(grid)

        # Remove temp item and draw permanent item in color
        if self._temp_item is not None:
            self._scene.removeItem(self._temp_item)
            self._temp_item = None

        self._roi_counter[tool] += 1
        label = f"{self._tool_label(tool)} {self._roi_counter[tool]}"
        color = self._color_palette[len(self.roi_list) % len(self._color_palette)]

        pixmap_rect = self._pixmap_item.pixmap().rect()
        scale_x = pixmap_rect.width() / self._grid_w
        scale_y = pixmap_rect.height() / self._grid_h

        permanent_item = None
        sx, sy = self._annotation_manager.points[0]
        ex, ey = grid
        
        p1 = self._grid_to_scene(sx, sy)
        p2 = self._grid_to_scene(ex, ey)
        x0 = min(p1.x(), p2.x())
        y0 = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x()) + scale_x
        h = abs(p2.y() - p1.y()) + scale_y

        if tool == AnnotationTool.RECT:
            rect = QRectF(x0, y0, w, h)
            permanent_item = self._scene.addRect(rect, self._make_pen(color, 1.0), self._make_brush(color, 40))
        elif tool == AnnotationTool.ELLIPSE:
            rect = QRectF(x0, y0, w, h)
            permanent_item = self._scene.addEllipse(rect, self._make_pen(color, 1.0), self._make_brush(color, 40))
        elif tool == AnnotationTool.LINE:
            permanent_item = self._scene.addLine(p1.x() + scale_x / 2, p1.y() + scale_y / 2, p2.x() + scale_x / 2, p2.y() + scale_y / 2, self._make_pen(color, 1.0))

        if permanent_item is not None:
            permanent_item.setZValue(5)
            self._drawing_items.append(permanent_item)

        roi_number = self._roi_counter[tool]
        self._add_roi_number_label(roi_number, x0 + 2, y0 - 14)

        mask = self._annotation_manager.generate_mask(self._grid_h, self._grid_w)
        if mask is not None:
            self.roi_list.append({
                "label": label,
                "mask": mask,
                "color": color
            })
            self.roi_list_changed.emit(self.roi_list)

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)

    def save_annotated_image(self, filepath: str) -> None:
        """Saves current scene contents including annotations."""
        if self._pixmap_item is None:
            return
        rect = self._pixmap_item.sceneBoundingRect()
        image = QImage(rect.size().toSize(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene.render(painter, QRectF(image.rect()), rect)
        painter.end()

        image.save(filepath)


# ============================================================================
# Spectrum graph widget (matplotlib plotting)
# (originally: ui/spectrum_graph_widget.py)
# ============================================================================

WAVELENGTHS = list(range(380, 781))


class SpectrumGraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._figure = Figure(figsize=(6, 4), facecolor="#ffffff")
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._ax = self._figure.add_subplot(111)
        self._configure_axes()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

    def _configure_axes(self) -> None:
        self._ax.clear()
        self._ax.set_facecolor("#ffffff")
        self._ax.set_title("Hyperspectral Spectrum Graph", color="#201f1e", fontsize=12, fontweight="bold", pad=12)
        self._ax.set_xlabel("Wavelength (nm)", color="#605e5c", fontsize=11, fontweight="bold")
        self._ax.set_ylabel("Intensity", color="#605e5c", fontsize=11, fontweight="bold")
        self._ax.tick_params(colors="#605e5c", labelsize=10)
        self._ax.grid(True, color="#d9d9d9", linewidth=0.8, linestyle="--")
        for spine in self._ax.spines.values():
            spine.set_color("#adadad")
        
        self._ax.text(
            0.5,
            0.5,
            "Select one or more ROIs to compare spectra",
            transform=self._ax.transAxes,
            ha="center",
            va="center",
            color="#8a8886",
            fontsize=11,
            style="italic"
        )
        self._ax.set_xlim(380, 780)
        self._ax.set_ylim(0, 1)

    def update_spectra(self, entries: list[dict]) -> None:
        self._ax.clear()
        if not entries:
            self._configure_axes()
            self._canvas.draw_idle()
            return

        for entry in entries:
            label = entry["label"]
            spectrum = entry["spectrum"]
            color = entry["color"]
            if spectrum is not None:
                self._ax.plot(
                    WAVELENGTHS,
                    spectrum,
                    color=color,
                    linewidth=2.2,
                    label=label
                )

        self._ax.set_facecolor("#ffffff")
        self._ax.set_title("Hyperspectral Spectrum Graph", color="#201f1e", fontsize=12, fontweight="bold", pad=12)
        self._ax.set_xlabel("Wavelength (nm)", color="#605e5c", fontsize=11, fontweight="bold")
        self._ax.set_ylabel("Intensity", color="#605e5c", fontsize=11, fontweight="bold")
        self._ax.tick_params(colors="#605e5c", labelsize=10)
        self._ax.grid(True, color="#d9d9d9", linewidth=0.8, linestyle="--")
        self._ax.set_xlim(380, 780)

        # Compute optimal limits for y axis
        all_y = [val for entry in entries if entry["spectrum"] is not None for val in entry["spectrum"]]
        if all_y:
            ymin, ymax = float(np.min(all_y)), float(np.max(all_y))
            y_range = ymax - ymin
            if y_range < 0.01:
                self._ax.set_ylim(max(0.0, ymin - 0.1), ymax + 0.1)
            else:
                self._ax.set_ylim(max(0.0, ymin - 0.05 * y_range), ymax + 0.05 * y_range)
        else:
            self._ax.set_ylim(0, 1)

        for spine in self._ax.spines.values():
            spine.set_color("#adadad")

        self._ax.legend(
            facecolor="#ffffff",
            edgecolor="#d1d1d1",
            labelcolor="#201f1e",
            fontsize=10,
            loc="upper right"
        )
        self._figure.tight_layout()
        self._canvas.draw_idle()

    def clear_graph(self) -> None:
        self.update_spectra([])


# ============================================================================
# Main window (assembles all widgets/controllers into the app UI)
# (originally: ui/main_window.py)
# ============================================================================

class ImageProcessWorker(QThread):
    finished = pyqtSignal(np.ndarray, np.ndarray)  # Emits (spectrum_array, block_image)
    failed = pyqtSignal(str)

    def __init__(self, analyzer: SpectrumAnalyzer, image: Image.Image, block_size: int = 8):
        super().__init__()
        self.analyzer = analyzer
        self.image = image
        self.block_size = block_size

    def run(self) -> None:
        try:
            spectrum_array, block_img = self.analyzer.process_image(self.image, self.block_size)
            self.finished.emit(spectrum_array, block_img)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, analyzer: SpectrumAnalyzer | None = None):
        super().__init__()
        self._analyzer = analyzer or SpectrumAnalyzer()
        self._camera_manager = CameraManager(self)
        self._worker: ImageProcessWorker | None = None

        self._current_spectrum_array: np.ndarray | None = None
        self._current_image_array: np.ndarray | None = None

        self.setWindowTitle("Hyperspectral Analysis System")
        self.setMinimumSize(1280, 780)
        self.setStyleSheet(WINDOWS_THEME)

        icon_path = _bundled_resource_path("logo.ico")
        if not os.path.exists(icon_path):
            icon_path = _bundled_resource_path("logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._connect_signals()
        self._update_button_states()

    def _build_ui(self) -> None:
        # Root widget and main vertical layout
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. TOP HEADER (Centered Project Name)
        header = QFrame()
        header.setObjectName("headerFrame")
        header.setStyleSheet("""
            QFrame#headerFrame {
                background-color: #ffffff;
                border-bottom: 1px solid #d1d1d1;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(12)

        header_layout.addStretch(1)

        # Project Name (centered)
        title_label = QLabel("Hyperspectral Analysis System")
        title_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #201f1e;")
        header_layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_layout.addStretch(1)

        main_layout.addWidget(header)

        # 2. MAIN SECTION (Single Image Display on Left, Graph on Right)
        central_container = QWidget()
        central_layout = QHBoxLayout(central_container)
        central_layout.setContentsMargins(14, 14, 14, 14)
        central_layout.setSpacing(14)

        # Single Image Display Widget
        display_frame = QFrame()
        display_frame.setObjectName("canvasFrame")
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(1, 1, 1, 1)

        self._display = ImageDisplayWidget()
        display_layout.addWidget(self._display)
        central_layout.addWidget(display_frame, 3)  # Left panel (image) - slightly reduced share

        # Single Multispectral Graph Widget
        graph_frame = QFrame()
        graph_frame.setObjectName("panel")
        graph_layout = QVBoxLayout(graph_frame)
        graph_layout.setContentsMargins(12, 12, 12, 12)

        self._graph = SpectrumGraphWidget()
        graph_layout.addWidget(self._graph)
        central_layout.addWidget(graph_frame, 2)  # Right panel (graph) - increased share

        main_layout.addWidget(central_container, 1)

        # 3. CONTROL PANEL (Logo + Controls Row)
        controls_frame = QFrame()
        controls_frame.setObjectName("panel")
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(16, 12, 16, 12)
        controls_layout.setSpacing(12)

        # Branding logo - fixed at the left of the control panel, beside "Load Image"
        logo_label = QLabel()
        logo_path = _bundled_resource_path("logo.png")
        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            logo_label.setPixmap(logo_pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
        else:
            logo_label.setText("[LAB LOGO]")
            logo_label.setStyleSheet("color: #605e5c; font-weight: bold;")
        controls_layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignVCenter)
        controls_layout.addSpacing(8)

        self._btn_load = QPushButton("Load Image")
        self._btn_camera = QPushButton("Connect Camera")
        self._btn_capture = QPushButton("Capture Image")
        self._btn_save = QPushButton("Save Image")
        self._id_label = QLabel("ID:")
        self._id_input = QLineEdit()
        self._id_input.setPlaceholderText("Required for export")
        self._id_input.setFixedWidth(140)
        self._btn_excel = QPushButton("Export Excel")
        self._btn_clear = QPushButton("Clear Annotation")
        self._btn_reset = QPushButton("Reset")

        # Classes for UI elements
        self._btn_load.setObjectName("primary")
        self._btn_camera.setObjectName("secondary")
        self._btn_capture.setObjectName("secondary")
        self._btn_save.setObjectName("secondary")
        self._btn_excel.setObjectName("secondary")
        self._btn_clear.setObjectName("secondary")
        self._btn_reset.setObjectName("danger")

        controls_layout.addWidget(self._btn_load)
        controls_layout.addWidget(self._btn_camera)
        controls_layout.addWidget(self._btn_capture)
        controls_layout.addWidget(self._btn_save)
        controls_layout.addWidget(self._id_label)
        controls_layout.addWidget(self._id_input)
        controls_layout.addWidget(self._btn_excel)
        controls_layout.addWidget(self._btn_clear)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self._btn_reset)

        main_layout.addWidget(controls_frame)

        # 4. STATUS BAR & PROGRESS
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)

        self._status = QStatusBar()
        self._status.showMessage("Ready. Load an image or connect camera to begin analysis.")
        self._status.addPermanentWidget(self._progress, 1)
        self.setStatusBar(self._status)

    def _connect_signals(self) -> None:
        self._btn_load.clicked.connect(self._load_image)
        self._btn_camera.clicked.connect(self._toggle_camera)
        self._btn_capture.clicked.connect(self._capture_image)
        self._btn_save.clicked.connect(self._save_image)
        self._btn_excel.clicked.connect(self._export_excel)
        self._btn_clear.clicked.connect(self._clear_annotation)
        self._btn_reset.clicked.connect(self._reset_app)

        self._camera_manager.frame_ready.connect(self._on_camera_frame)
        self._display.roi_list_changed.connect(self._on_roi_list_changed)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._progress.setVisible(busy)
        self._btn_load.setEnabled(not busy)
        self._btn_camera.setEnabled(not busy)
        self._btn_reset.setEnabled(not busy)
        if message:
            self._status.showMessage(message)

    def _load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"
        )
        if not path:
            return

        try:
            img = Image.open(path)
            self._start_processing(img, label=os.path.basename(path))
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", f"Could not load image: {exc}")

    def _start_processing(self, img: Image.Image, label: str) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._set_busy(True, f"Analyzing {label}...")
        self._worker = ImageProcessWorker(self._analyzer, img, block_size=8)
        self._worker.finished.connect(lambda spec, img_arr: self._on_process_finished(spec, img_arr, label))
        self._worker.failed.connect(self._on_process_failed)
        self._worker.start()

    def _on_process_finished(self, spectrum_array: np.ndarray, block_image: np.ndarray, label: str) -> None:
        self._set_busy(False)
        self._current_spectrum_array = spectrum_array
        self._current_image_array = block_image

        # Crop the original image to match the block grid dimensions for high-quality display
        original_img_np = None
        if self._worker and self._worker.image:
            img = self._worker.image
            block_size = self._worker.block_size
            grid_w = img.width // block_size
            grid_h = img.height // block_size
            cropped_img = img.crop((0, 0, grid_w * block_size, grid_h * block_size)).convert("RGB")
            original_img_np = np.array(cropped_img, dtype=np.uint8)

        self._display.set_image(block_image, original_img_np)
        self._graph.clear_graph()

        self._status.showMessage(f"Loaded {label}. Reconstructed {spectrum_array.shape[1]}x{spectrum_array.shape[0]} spectral grid.")
        self._update_button_states()

    def _on_process_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Processing Error", message)
        self._status.showMessage("Processing failed.")
        self._update_button_states()

    def _on_camera_frame(self, frame: np.ndarray) -> None:
        self._display.set_camera_frame(frame)

    def _toggle_camera(self) -> None:
        if self._camera_manager.is_active():
            self._camera_manager.stop_camera()
            self._display.clear_all()
            self._status.showMessage("Camera disconnected.")
        else:
            self._clear_data()
            self._display.clear_all()
            self._graph.clear_graph()
            self._status.showMessage("Searching for connected camera...")
            QApplication.processEvents()

            # Automatically probe connected cameras (prefer external USB cameras connected via cable)
            available = UniversalVideoCapture.get_available_cameras(max_tested=6)
            external_candidates = [idx for idx in available if idx != 0]
            candidates = external_candidates + ([0] if (0 in available or not available) else [])

            if not candidates:
                candidates = [1, 2, 0]

            connected_index = None
            for idx in candidates:
                self._status.showMessage(f"Connecting to camera (device {idx})...")
                QApplication.processEvents()
                if self._camera_manager.start_camera(idx):
                    connected_index = idx
                    break

            if connected_index is not None:
                if connected_index > 0:
                    self._status.showMessage(f"External camera (device {connected_index}) connected. Streaming live feed...")
                else:
                    self._status.showMessage("Camera connected. Streaming live feed...")
            else:
                self._status.showMessage("Error: Could not connect to camera.")
                QMessageBox.warning(
                    self,
                    "Camera Error",
                    "Could not connect to any camera.\n\n"
                    "Suggestions:\n"
                    "1. Ensure your external camera USB cable is plugged in securely.\n"
                    "2. Verify no other application (e.g. Windows Camera, Zoom, Teams) is using the device."
                )
        self._update_button_states()

    def _capture_image(self) -> None:
        frame = self._camera_manager.capture_frame()
        if frame is None:
            QMessageBox.warning(self, "Capture Error", "No camera frame available.")
            return

        self._camera_manager.stop_camera()
        img = Image.fromarray(frame)
        self._start_processing(img, label="Camera Capture")

    def _save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Annotated Image",
            "annotated_image.png",
            "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;BMP Files (*.bmp)"
        )
        if not path:
            return
        try:
            self._display.save_annotated_image(path)
            self._status.showMessage(f"Saved annotated image to {os.path.basename(path)}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Could not save annotated image: {exc}")

    def _get_exports_dir(self) -> str:
        """Returns the project's Exports folder, creating it if needed."""
        exports_dir = os.path.join(_app_base_dir(), "Exports")
        os.makedirs(exports_dir, exist_ok=True)
        return exports_dir

    def _open_in_explorer(self, folder_path: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))

    def _sanitize_filename(self, name: str) -> str:
        """Strips characters that are invalid in Windows filenames."""
        invalid_chars = '<>:"/\\|?*'
        cleaned = "".join(c for c in name if c not in invalid_chars and ord(c) >= 32)
        return cleaned.strip().strip(".")

    def _export_excel(self) -> None:
        if self._current_spectrum_array is None:
            return
        if not self._display.roi_list:
            QMessageBox.warning(self, "Export Warning", "No active ROI annotations found. Please draw at least one ROI to export.")
            return
        custom_id = self._sanitize_filename(self._id_input.text())
        if not custom_id:
            QMessageBox.warning(self, "ID Required", "Please enter an ID before exporting the Excel file.")
            return
        self._set_busy(True, "Generating Excel...")
        try:
            data = to_excel_bytes_roi(self._display.roi_list, self._current_spectrum_array, self._analyzer)
            exports_dir = self._get_exports_dir()
            path = os.path.join(exports_dir, f"{custom_id}.xlsx")
            with open(path, "wb") as fh:
                fh.write(data)
            self._status.showMessage(f"Saved Excel export to Exports/{os.path.basename(path)}")
            self._open_in_explorer(exports_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Could not save Excel export: {exc}")
        finally:
            self._set_busy(False)
            self._update_button_states()

    def _clear_annotation(self) -> None:
        self._display.clear_annotations()
        self._graph.clear_graph()
        self._update_button_states()

    def _reset_app(self) -> None:
        self._camera_manager.stop_camera()
        self._clear_data()
        self._display.clear_all()
        self._graph.clear_graph()
        self._status.showMessage("System reset.")
        self._update_button_states()

    def _clear_data(self) -> None:
        self._current_spectrum_array = None
        self._current_image_array = None

    def _on_roi_list_changed(self, roi_list: list[dict]) -> None:
        if self._current_spectrum_array is None:
            return
        plot_entries = []
        supported_types = {"Rectangle", "Ellipse", "Point", "Polygon"}
        for roi in roi_list:
            label = roi.get("label", "")
            roi_type = label.split()[0] if label else "Unknown"
            if roi_type not in supported_types:
                continue
            avg_spectrum = self._analyzer.get_roi_spectrum(self._current_spectrum_array, roi["mask"])
            if avg_spectrum is not None:
                plot_entries.append({
                    "label": roi["label"],
                    "spectrum": avg_spectrum,
                    "color": roi["color"]
                })
        self._graph.update_spectra(plot_entries)
        self._update_button_states()

    def _update_button_states(self) -> None:
        camera_active = self._camera_manager.is_active()
        has_image = self._current_image_array is not None
        
        # Only count active supported ROIs
        supported_types = {"Rectangle", "Ellipse", "Point", "Polygon"}
        active_supported_rois = 0
        for roi in self._display.roi_list:
            label = roi.get("label", "")
            roi_type = label.split()[0] if label else "Unknown"
            if roi_type in supported_types:
                active_supported_rois += 1
        has_points = active_supported_rois > 0

        self._btn_load.setEnabled(not camera_active)

        if camera_active:
            self._btn_camera.setText("Disconnect Camera")
        else:
            self._btn_camera.setText("Connect Camera")
        self._btn_camera.setEnabled(True)

        self._btn_capture.setEnabled(camera_active)
        self._btn_save.setEnabled(has_image)
        self._btn_excel.setEnabled(has_image and has_points)
        self._btn_clear.setEnabled(has_image and has_points)
        self._btn_reset.setEnabled(True)

    def closeEvent(self, event) -> None:
        self._camera_manager.stop_camera()
        if self._worker and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)


# ============================================================================
# Application entry point
# (originally: main.py)
# ============================================================================

def excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    import traceback
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print("Unhandled Exception:", err_msg, file=sys.stderr)
    try:
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("Application Error")
        msg_box.setText(f"An unexpected error occurred:\n{exc_value}")
        msg_box.setDetailedText(err_msg)
        msg_box.exec()
    except Exception:
        pass


def main() -> int:
    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    app.setApplicationName("Hyperspectral Analysis System")
    app.setOrganizationName("Hyperspectral Analysis System")

    icon_path = _bundled_resource_path("logo.ico")
    if not os.path.exists(icon_path):
        icon_path = _bundled_resource_path("logo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    analyzer = SpectrumAnalyzer()
    window = MainWindow(analyzer)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

