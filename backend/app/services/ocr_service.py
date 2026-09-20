import logging
import pytesseract
from PIL import Image
from typing import Optional

logger = logging.getLogger(__name__)

class OCRService:
    def extract_text(self, image: Image.Image) -> str:
        """
        Extract text from an image using Tesseract OCR.
        Returns the extracted text or an empty string on failure.
        """
        try:
            text = pytesseract.image_to_string(image)
            return text.strip()
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ""

ocr_service = OCRService()
