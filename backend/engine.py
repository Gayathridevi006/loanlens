"""
OCR Engine — Image preprocessing and Tesseract text extraction.
No external AI API required — runs fully on-device.
"""

import io
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import pytesseract

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Multi-stage image preprocessing pipeline to maximise OCR accuracy.
    Each stage can be toggled for different document types.
    """

    @staticmethod
    def to_grayscale(img: Image.Image) -> Image.Image:
        return img.convert("L")

    @staticmethod
    def denoise(img: Image.Image, size: int = 3) -> Image.Image:
        return img.filter(ImageFilter.MedianFilter(size=size))

    @staticmethod
    def sharpen(img: Image.Image) -> Image.Image:
        return img.filter(ImageFilter.SHARPEN)

    @staticmethod
    def enhance_contrast(img: Image.Image, factor: float = 2.0) -> Image.Image:
        return ImageEnhance.Contrast(img).enhance(factor)

    @staticmethod
    def binarize(img: Image.Image, threshold: int = 128) -> Image.Image:
        """Otsu-style threshold binarisation."""
        return img.point(lambda p: 255 if p > threshold else 0)

    @staticmethod
    def deskew(img: Image.Image) -> Image.Image:
        """Auto-rotate using OSD if possible."""
        try:
            osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
            angle = osd.get("rotate", 0)
            if angle and angle != 0:
                img = img.rotate(-angle, expand=True, fillcolor=255)
        except Exception:
            pass  # OSD can fail on low-quality images
        return img

    @staticmethod
    def upscale_if_small(img: Image.Image, min_width: int = 1000) -> Image.Image:
        w, h = img.size
        if w < min_width:
            scale = min_width / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        return img

    @classmethod
    def full_pipeline(cls, img: Image.Image) -> Image.Image:
        """Run all preprocessing steps in sequence."""
        img = cls.upscale_if_small(img)
        img = cls.to_grayscale(img)
        img = cls.denoise(img)
        img = cls.enhance_contrast(img)
        img = cls.sharpen(img)
        img = cls.binarize(img)
        img = cls.deskew(img)
        return img

    @classmethod
    def light_pipeline(cls, img: Image.Image) -> Image.Image:
        """Lighter preprocessing for already-clean digital documents."""
        img = cls.upscale_if_small(img)
        img = cls.to_grayscale(img)
        img = cls.enhance_contrast(img, factor=1.5)
        return img


class OCRResult:
    """Structured OCR result with confidence metadata."""

    def __init__(self, text: str, word_count: int, char_count: int):
        self.text = text
        self.word_count = word_count
        self.char_count = char_count

    @property
    def confidence(self) -> str:
        if self.word_count > 120:
            return "HIGH"
        elif self.word_count > 40:
            return "MEDIUM"
        else:
            return "LOW"

    @property
    def is_usable(self) -> bool:
        return self.word_count >= 5

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "confidence": self.confidence,
            "is_usable": self.is_usable,
        }


class OCREngine:
    """
    Main OCR engine. Accepts PIL Images, file paths, or base64 strings.
    Uses Tesseract 5 under the hood — no API keys needed.
    """

    # Tesseract configs for different scenarios
    CONFIGS = {
        "default":    r"--oem 3 --psm 6",   # Uniform block of text
        "sparse":     r"--oem 3 --psm 11",  # Sparse text (find as much as possible)
        "single_col": r"--oem 3 --psm 4",   # Single column
        "table":      r"--oem 3 --psm 6 -c preserve_interword_spaces=1",
    }

    @classmethod
    def extract_from_image(
        cls,
        img: Image.Image,
        mode: str = "default",
        preprocess: bool = True,
    ) -> OCRResult:
        """Extract text from a PIL Image."""
        if preprocess:
            # Try full pipeline first; fall back to light if result is poor
            processed = ImagePreprocessor.full_pipeline(img.copy())
            text = pytesseract.image_to_string(processed, config=cls.CONFIGS.get(mode, cls.CONFIGS["default"]))

            if len(text.split()) < 10:
                # Retry with lighter preprocessing
                processed = ImagePreprocessor.light_pipeline(img.copy())
                text2 = pytesseract.image_to_string(processed, config=cls.CONFIGS["sparse"])
                if len(text2.split()) > len(text.split()):
                    text = text2
        else:
            text = pytesseract.image_to_string(img, config=cls.CONFIGS.get(mode, cls.CONFIGS["default"]))

        text = text.strip()
        return OCRResult(
            text=text,
            word_count=len(text.split()),
            char_count=len(text),
        )

    @classmethod
    def extract_from_path(cls, path: str | Path, **kwargs) -> OCRResult:
        img = Image.open(str(path))
        return cls.extract_from_image(img, **kwargs)

    @classmethod
    def extract_from_base64(cls, b64_string: str, **kwargs) -> Tuple[Image.Image, OCRResult]:
        """
        Accept a full data URI (data:image/png;base64,...) or raw base64.
        Returns (original_image, OCRResult).
        """
        if "," in b64_string:
            b64_string = b64_string.split(",", 1)[1]
        raw = base64.b64decode(b64_string)
        img = Image.open(io.BytesIO(raw))
        result = cls.extract_from_image(img, **kwargs)
        return img, result

    @classmethod
    def extract_from_pdf_bytes(cls, pdf_bytes: bytes) -> list[OCRResult]:
        """
        Convert PDF pages to images and OCR each page.
        Requires poppler (pdf2image).
        """
        try:
            from pdf2image import convert_from_bytes
            pages = convert_from_bytes(pdf_bytes, dpi=200)
            return [cls.extract_from_image(page) for page in pages]
        except ImportError:
            logger.warning("pdf2image not installed. Install with: pip install pdf2image")
            return []

    @classmethod
    def extract_best(cls, b64_string: str) -> Tuple[Image.Image, OCRResult]:
        """
        Try multiple Tesseract configs and return the best OCR result.
        Useful for difficult documents.
        """
        if "," in b64_string:
            raw = base64.b64decode(b64_string.split(",", 1)[1])
        else:
            raw = base64.b64decode(b64_string)

        img = Image.open(io.BytesIO(raw))
        best: Optional[OCRResult] = None

        for mode in ["default", "single_col", "sparse"]:
            try:
                result = cls.extract_from_image(img.copy(), mode=mode)
                if best is None or result.word_count > best.word_count:
                    best = result
            except Exception as e:
                logger.warning(f"OCR mode {mode} failed: {e}")

        return img, best or OCRResult("", 0, 0)


class PDFOCREngine:
    """Handle multi-page PDF documents."""

    @classmethod
    def from_bytes(cls, pdf_bytes: bytes) -> list[OCRResult]:
        return OCREngine.extract_from_pdf_bytes(pdf_bytes)

    @classmethod
    def from_base64(cls, b64: str) -> list[OCRResult]:
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64)
        return cls.from_bytes(raw)

    @classmethod
    def merge_pages(cls, results: list[OCRResult]) -> OCRResult:
        """Merge multi-page OCR results into one."""
        combined = "\n\n--- PAGE BREAK ---\n\n".join(r.text for r in results)
        return OCRResult(
            text=combined,
            word_count=sum(r.word_count for r in results),
            char_count=sum(r.char_count for r in results),
        )
