import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ChunkingService:
    def chunk_elements(self, elements: List[Dict[str, Any]], chunk_size: int = 1500, overlap: int = 300) -> List[Dict[str, Any]]:
        """
        Creates semantic chunks from parsed document elements.
        Tables and Figures are kept as distinct chunks.
        Text elements are grouped together up to chunk_size.
        """
        chunks = []
        current_text = ""
        current_pages = []
        
        def finalize_text_chunk():
            nonlocal current_text, current_pages
            if current_text.strip():
                text_splits = self._split_text(current_text, chunk_size, overlap)
                for s in text_splits:
                    if len(s) > 10:
                        chunks.append({
                            "type": "text",
                            "text": s,
                            "page": current_pages[0] if current_pages else 1,
                        })
            current_text = ""
            current_pages = []

        for el in elements:
            if el["type"] == "text":
                current_text += el["text"] + "\n\n"
                current_pages.append(el["page"])
            elif el["type"] in ["table", "figure"]:
                finalize_text_chunk()
                content_text = ""
                
                analysis = el.get("visual_analysis", {})
                
                if el["type"] == "table":
                    content_text = f"[TABLE]\n"
                    if "title" in analysis:
                        content_text += f"Title: {analysis['title']}\n"
                    content_text += f"{el.get('text', '')}\n"
                else:
                    content_text = f"[FIGURE]\n"
                    if "figure_type" in analysis:
                        content_text += f"Type: {analysis['figure_type']}\n"
                
                if el.get("caption"):
                    content_text += f"Caption: {el['caption']}\n"
                    
                if analysis.get("description"):
                    content_text += f"Visual Analysis: {analysis.get('description', '')}\n"
                    
                if analysis.get("text_content"):
                    content_text += f"Embedded Text: {analysis.get('text_content', '')}\n"

                # If vision and OCR failed, at least tell the LLM explicitly
                if "Failed to analyze" in analysis.get("description", ""):
                    content_text += "[NOTE: The visual contents of this element could not be analyzed due to missing Vision API / OCR tools. Only the caption and surrounding text are available.]\n"

                # Add preceding and succeeding text blocks for context
                context_blocks = []
                # Simple heuristic: grab the text of the element immediately before and after this one
                el_index = elements.index(el)
                if el_index > 0 and elements[el_index - 1]["type"] == "text":
                    context_blocks.append(f"Text before {el['type']}: {elements[el_index - 1]['text'][:500]}")
                if el_index < len(elements) - 1 and elements[el_index + 1]["type"] == "text":
                    context_blocks.append(f"Text after {el['type']}: {elements[el_index + 1]['text'][:500]}")
                
                if context_blocks:
                    content_text += "\nSurrounding Context:\n" + "\n".join(context_blocks) + "\n"

                chunks.append({
                    "type": el["type"],
                    "text": content_text.strip(),
                    "page": el["page"],
                })
            elif el["type"] == "caption":
                if "associated_to" not in el:
                    current_text += el["text"] + "\n\n"
                    current_pages.append(el["page"])

        finalize_text_chunk()
        return chunks

    def _split_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        text = re.sub(r'([a-z])-\n([a-z])', r'\1\2', text)
        separators = ["\n\n", "\n", ". ", " "]
        
        def do_split(txt: str, seps: List[str]) -> List[str]:
            if not seps:
                return [txt[i:i+chunk_size] for i in range(0, len(txt), chunk_size)]
            sep = seps[0]
            parts = txt.split(sep)
            res = []
            cur = ""
            for p in parts:
                if not p.strip(): continue
                add_sep = sep if cur else ""
                if len(cur) + len(add_sep) + len(p) <= chunk_size:
                    cur += add_sep + p
                else:
                    if cur: res.append(cur)
                    if len(p) > chunk_size:
                        sub = do_split(p, seps[1:])
                        res.extend(sub[:-1])
                        cur = sub[-1] if sub else ""
                    else:
                        cur = p
            if cur: res.append(cur)
            return res

        splits = do_split(text, separators)
        final_splits = []
        for i, s in enumerate(splits):
            if i > 0 and overlap > 0:
                prev = splits[i-1]
                overlap_txt = prev[-overlap:]
                boundary = max(overlap_txt.find('. '), overlap_txt.find('\n'))
                if boundary != -1:
                    cutoff = boundary + 2 if overlap_txt[boundary:boundary+2] == '. ' else boundary + 1
                    overlap_txt = overlap_txt[cutoff:]
                s = overlap_txt.strip() + " " + s.strip()
            final_splits.append(s.strip())
            
        return final_splits

chunking_service = ChunkingService()
