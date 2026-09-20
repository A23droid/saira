import logging
import base64
import io
from typing import Dict, Any, Optional
from PIL import Image

from app.services.groq_service import groq_service

logger = logging.getLogger(__name__)

class VisionService:
    async def analyze_visual(self, image: Image.Image, element_type: str, caption: Optional[str] = None) -> Dict[str, Any]:
        """
        Uses a vision model to generate a structured description of a figure or table.
        element_type should be "figure" or "table".
        """
        try:
            # Convert PIL image to base64
            buffered = io.BytesIO()
            # Convert to RGB to avoid issues with alpha channels in JPEG
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            image.save(buffered, format="JPEG", quality=85)
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            prompt = f"""You are an expert academic research assistant. 
Analyze the provided {element_type} from a research paper.
"""
            if caption:
                prompt += f"The caption for this {element_type} is: {caption}\n"
                
            prompt += """
Provide a structured JSON description. Do NOT hallucinate values that are unreadable or uncertain.

If it is a table, return JSON like:
{
    "type": "table",
    "title": "Extracted or inferred title",
    "headers": ["Col1", "Col2"],
    "rows": [["Val1", "Val2"]],
    "description": "A detailed semantic description of the table's purpose and key results."
}

If it is a figure/graph/chart, return JSON like:
{
    "type": "figure",
    "figure_type": "Line chart / Bar chart / Diagram / etc.",
    "x_axis": "Label of X axis if applicable",
    "y_axis": "Label of Y axis if applicable",
    "series": ["List of legends/categories"],
    "description": "A detailed semantic description of what the figure shows, trends, and relationships. If values are exact, state them, else state they are approximate.",
    "text_content": "Any readable text from the figure (OCR equivalent)"
}
"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}}
                    ]
                }
            ]
            
            # Use Llama 3.2 Vision on Groq
            result = await groq_service.chat_complete_json(
                model="llama-3.2-90b-vision",
                messages=messages,
                temperature=0.1,
                max_tokens=2048,
            )
            return result
        except Exception as e:
            logger.warning(f"Vision analysis failed for {element_type} (model error): {e}")
            
            # Fallback to OCR since vision model failed
            try:
                from app.services.ocr_service import ocr_service
                text = ocr_service.extract_text(image)
                if text:
                    return {
                        "description": f"Visual analysis unavailable. Extracted text via OCR.",
                        "text_content": text
                    }
            except Exception as ocr_e:
                logger.warning(f"OCR fallback also failed: {ocr_e}")
                
            return {"error": str(e), "description": f"Failed to analyze {element_type} visually."}

vision_service = VisionService()
