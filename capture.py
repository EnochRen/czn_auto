import numpy as np
import cv2
import dxcam
from typing import Tuple


class ScreenCapturer:
    def __init__(self, method: str = "auto"):
        self.camera = dxcam.create(output_color="BGR")
        self.method = method
        self.last_resolution = (1920, 1080)

    def capture(self) -> np.ndarray:
        img = self.camera.grab()
        if img is None:
            img = self.camera.grab()
        if img is None:
            return np.zeros((self.last_resolution[1], self.last_resolution[0], 3), dtype=np.uint8)
        self.last_resolution = (img.shape[1], img.shape[0])
        return img

    def get_resolution(self) -> Tuple[int, int]:
        return self.last_resolution
