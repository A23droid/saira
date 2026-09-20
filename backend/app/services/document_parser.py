import logging
import io
from typing import List, Dict, Any, Optional
import fitz
from PIL import Image

logger = logging.getLogger(__name__)

class DocumentParser:
    def parse(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Parses a PDF into structured elements: Text, Table, Figure, Caption.
        Returns a list of elements with metadata.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        elements = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # 1. Extract Tables
            try:
                tables = page.find_tables()
                table_bboxes = []
                if tables and tables.tables:
                    for i, table in enumerate(tables.tables):
                        table_bboxes.append(table.bbox)
                        extracted = table.extract()
                        if extracted:
                            # Clean up None values
                            cleaned_rows = [["" if c is None else str(c).strip() for c in row] for row in extracted]
                            text_repr = "\n".join(["\t".join(row) for row in cleaned_rows])
                            elements.append({
                                "type": "table",
                                "page": page_num + 1,
                                "bbox": table.bbox,
                                "content": cleaned_rows,
                                "text": text_repr
                            })
            except Exception as e:
                logger.warning(f"Failed to extract tables on page {page_num + 1}: {e}")
                table_bboxes = []

            # 2. Extract Blocks (Text and Images)
            try:
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    bbox = block.get("bbox")
                    if not bbox: continue
                    
                    # Check if block overlaps with any table. If so, skip it to avoid duplication.
                    is_in_table = False
                    for t_bbox in table_bboxes:
                        if self._intersects(bbox, t_bbox):
                            is_in_table = True
                            break
                    if is_in_table:
                        continue

                    if block.get("type") == 0:  # Text
                        text = ""
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                text += span.get("text", "") + " "
                            text += "\n"
                        text = text.strip()
                        if text:
                            elements.append({
                                "type": "text",
                                "page": page_num + 1,
                                "bbox": bbox,
                                "text": text
                            })
                    elif block.get("type") == 1:  # Image
                        image_bytes = block.get("image")
                        if image_bytes:
                            try:
                                img = Image.open(io.BytesIO(image_bytes))
                                elements.append({
                                    "type": "figure",
                                    "page": page_num + 1,
                                    "bbox": bbox,
                                    "image": img
                                })
                            except Exception as e:
                                logger.warning(f"Failed to load image on page {page_num + 1}: {e}")
            except Exception as e:
                logger.warning(f"Failed to extract blocks on page {page_num + 1}: {e}")

        doc.close()
        
        # Post-processing: Associate captions with figures/tables
        elements = self._associate_captions(elements)
        
        return elements

    def _intersects(self, bbox1, bbox2):
        x0_1, y0_1, x1_1, y1_1 = bbox1
        x0_2, y0_2, x1_2, y1_2 = bbox2
        return not (x1_1 <= x0_2 or x0_1 >= x1_2 or y1_1 <= y0_2 or y0_1 >= y1_2)

    def _associate_captions(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for i, el in enumerate(elements):
            if el["type"] == "text":
                text_lower = el["text"].lower()
                if text_lower.startswith("fig.") or text_lower.startswith("figure") or text_lower.startswith("table"):
                    # Find nearest figure/table on the same page
                    nearest = None
                    min_dist = float('inf')
                    for j, other in enumerate(elements):
                        if other["type"] in ["figure", "table"] and other["page"] == el["page"]:
                            # calculate vertical distance
                            # caption can be above or below
                            dist_below = abs(el["bbox"][1] - other["bbox"][3]) # top of text to bottom of figure
                            dist_above = abs(other["bbox"][1] - el["bbox"][3]) # top of figure to bottom of text
                            dist = min(dist_below, dist_above)
                            
                            if dist < min_dist and dist < 150: # threshold
                                min_dist = dist
                                nearest = other
                    
                    if nearest:
                        el["type"] = "caption"
                        el["associated_to"] = nearest["type"]
                        if "caption" not in nearest:
                            nearest["caption"] = el["text"]
                        else:
                            nearest["caption"] += "\n" + el["text"]
                            
        return elements

document_parser = DocumentParser()
