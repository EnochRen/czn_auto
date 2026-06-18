import io
import logging
import numpy as np

try:
    from paddleocr import PaddleOCR
    _PADDLE_AVAILABLE = True
except ImportError:
    _PADDLE_AVAILABLE = False
import cv2
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class OcrBackend:
    def scan(self, frame: np.ndarray, region: Optional[list] = None
             ) -> List[Tuple[str, int, int, int, int]]:
        raise NotImplementedError

    def find_text(self, frame: np.ndarray, keyword: str,
                  region: Optional[list] = None,
                  consecutive: bool = False) -> Optional[Tuple[int, int]]:
        texts = self.scan(frame, region)
        for text, bx, by, bw, bh in texts:
            if keyword in text:
                cx = bx + bw // 2
                cy = by + bh // 2
                logger.info(f"OCR 精确匹配「{keyword}」: 「{text}」 at ({cx}, {cy})")
                return (cx, cy)
        if consecutive and len(keyword) > 1:
            chars = list(keyword)
            sorted_words = sorted(texts, key=lambda t: (t[2], t[1]))
            for i in range(len(sorted_words) - len(chars) + 1):
                ok = True
                for j, ch in enumerate(chars):
                    if sorted_words[i+j][0] != ch:
                        ok = False
                        break
                if ok:
                    xs = [sorted_words[i+j][1] for j in range(len(chars))]
                    ys = [sorted_words[i+j][2] for j in range(len(chars))]
                    x_rs = [sorted_words[i+j][3] for j in range(len(chars))]
                    y_rs = [sorted_words[i+j][4] for j in range(len(chars))]
                    min_x = min(xs)
                    max_x = max(xs[j] + x_rs[j] for j in range(len(chars)))
                    min_y = min(ys)
                    max_y = max(ys[j] + y_rs[j] for j in range(len(chars)))
                    cx = (min_x + max_x) // 2
                    cy = (min_y + max_y) // 2
                    logger.info(f"OCR 连续匹配「{keyword}」 at ({cx}, {cy})")
                    return (cx, cy)
        return None


class WindowsOcrBackend(OcrBackend):
    def __init__(self, lang: str = "zh-cn"):
        import winrt.windows.media.ocr as wocr
        import winrt.windows.globalization as wgl
        import winrt.windows.graphics.imaging as wimg
        import winrt.windows.storage.streams as wss
        self._wocr = wocr
        self._wgl = wgl
        self._wimg = wimg
        self._wss = wss
        self._lang = lang
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        lang = self._wgl.Language(self._lang)
        self._engine = self._wocr.OcrEngine.try_create_from_language(lang)
        if self._engine:
            logger.info(f"Windows OCR 已初始化: {self._lang}")
        else:
            logger.warning(f"Windows OCR 语言 {self._lang} 不受支持，用 zh-cn 兜底")
            self._engine = self._wocr.OcrEngine.try_create_from_language(
                self._wgl.Language("zh-cn"))

    def _frame_to_bitmap(self, frame: np.ndarray):
        ret, buf = cv2.imencode(".png", frame)
        data = buf.tobytes()
        stream = self._wss.InMemoryRandomAccessStream()
        stream.write_async(data).get()
        stream.seek(0)
        decoder = self._wimg.BitmapDecoder.create_async(stream).get()
        return decoder.get_software_bitmap_async().get()

    def scan(self, frame: np.ndarray, region: Optional[list] = None
             ) -> List[Tuple[str, int, int, int, int]]:
        if self._engine is None:
            return []
        if region:
            x, y, w, h = region
            frame = frame[y:y+h, x:x+w]
        else:
            x, y = 0, 0
        try:
            bitmap = self._frame_to_bitmap(frame)
            result = self._engine.recognize_async(bitmap).get()
            texts = []
            for line in result.lines:
                text = line.text.strip()
                if not text:
                    continue
                for word in line.words:
                    wt = word.text.strip()
                    if not wt:
                        continue
                    bx = int(word.bounding_rect.x) + x
                    by = int(word.bounding_rect.y) + y
                    bw = int(word.bounding_rect.width)
                    bh = int(word.bounding_rect.height)
                    texts.append((wt, bx, by, bw, bh))
            return texts
        except Exception as e:
            logger.error(f"Windows OCR 识别失败: {e}")
            return []

    def set_lang(self, lang: str):
        if lang != self._lang:
            self._lang = lang
            self._init_engine()


class PaddleOcrBackend(OcrBackend):
    def __init__(self, lang: str = "ch"):
        if not _PADDLE_AVAILABLE:
            raise ImportError("paddleocr 未安装，请执行: pip install paddleocr")
        self._ocr = PaddleOCR(use_angle_cls=False, lang=lang)
        self._lang = lang
        logger.info(f"PaddleOCR 已初始化: {lang}")

    def scan(self, frame: np.ndarray, region: Optional[list] = None
             ) -> List[Tuple[str, int, int, int, int]]:
        if region:
            x, y, w, h = region
            crop = frame[y:y+h, x:x+w]
        else:
            crop = frame
            x, y = 0, 0
        try:
            result = self._ocr.ocr(crop, cls=False)
            texts = []
            if result and result[0]:
                for line in result[0]:
                    box, (txt, conf) = line
                    pts = np.array(box, dtype=np.int32)
                    bx = int(pts[:, 0].min()) + x
                    by = int(pts[:, 1].min()) + y
                    bw = int(pts[:, 0].max()) - int(pts[:, 0].min())
                    bh = int(pts[:, 1].max()) - int(pts[:, 1].min())
                    t = txt.strip()
                    if t:
                        texts.append((t, bx, by, bw, bh))
            return texts
        except Exception as e:
            logger.error(f"PaddleOCR 识别失败: {e}")
            return []

    def set_lang(self, lang: str):
        pass


_BACKENDS = {
    "windows": WindowsOcrBackend,
    "paddle": PaddleOcrBackend,
}


class OcrReader:
    def __init__(self, lang: str = "zh-cn", backend: str = "windows"):
        self._lang = lang
        self._backend_name = backend
        cls = _BACKENDS.get(backend)
        if cls is None:
            logger.warning(f"未知 OCR 后端 {backend}，使用 windows")
            cls = WindowsOcrBackend
        paddle_lang = "ch" if lang.startswith("zh") else "en"
        if cls is PaddleOcrBackend:
            self._impl = cls(lang=paddle_lang)
        else:
            self._impl = cls(lang=lang)

    def scan(self, frame: np.ndarray, region: Optional[list] = None
             ) -> List[Tuple[str, int, int, int, int]]:
        return self._impl.scan(frame, region)

    def find_text(self, frame: np.ndarray, keyword: str,
                  region: Optional[list] = None,
                  consecutive: bool = False) -> Optional[Tuple[int, int]]:
        return self._impl.find_text(frame, keyword, region, consecutive)

    def set_lang(self, lang: str):
        self._lang = lang
        self._impl.set_lang(lang)
