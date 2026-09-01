import logging
import time
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)

# TTL Cache dictionary: url -> (timestamp, result)
# Valid TTL: 24 hours, Invalid TTL: 1 hour
VALID_TTL = 24 * 3600
INVALID_TTL = 1 * 3600

_validation_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}

def _get_from_cache(url: str) -> Optional[Dict[str, Any]]:
    if url in _validation_cache:
        timestamp, result = _validation_cache[url]
        ttl = VALID_TTL if result.get("valid") else INVALID_TTL
        if time.time() - timestamp < ttl:
            return result
        else:
            del _validation_cache[url]
    return None

def _save_to_cache(url: str, result: Dict[str, Any]) -> None:
    # Very basic size bounding to prevent memory leaks in long-running processes
    if len(_validation_cache) > 10000:
        # Clear out a chunk of the cache
        keys_to_delete = list(_validation_cache.keys())[:2000]
        for k in keys_to_delete:
            _validation_cache.pop(k, None)
    _validation_cache[url] = (time.time(), result)


class PDFValidator:
    async def validate_pdf_url(self, url: str) -> Dict[str, Any]:
        """
        Validates if a URL points to an actual PDF.
        Returns:
            {"valid": True, "url": final_url, "content_type": type}
            {"valid": False, "url": url, "reason": "..."}
        """
        if not url:
            return {"valid": False, "url": url, "reason": "empty_url"}
            
        cached = _get_from_cache(url)
        if cached:
            return cached

        # Attempt a bounded GET request. HEAD is often blocked or unsupported 
        # by academic providers (e.g. they return 405 or just HTML instead of PDF on HEAD).
        headers = {
            "User-Agent": "SAIRA/1.0 (Research Assistant) Mozilla/5.0",
            "Accept": "application/pdf, application/octet-stream, */*"
        }

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code >= 400:
                        result = {"valid": False, "url": url, "reason": f"status_{response.status_code}"}
                        _save_to_cache(url, result)
                        return result
                    
                    final_url = str(response.url)
                    
                    content_type = response.headers.get("content-type", "").lower()
                    if "text/html" in content_type:
                        result = {"valid": False, "url": final_url, "reason": "is_html_page"}
                        _save_to_cache(url, result)
                        return result
                    
                    # Read first chunk for magic bytes `%PDF-`
                    chunk = b""
                    async for c in response.aiter_bytes(chunk_size=2048):
                        chunk = c
                        break
                    
                    if not chunk:
                        result = {"valid": False, "url": final_url, "reason": "empty_response"}
                        _save_to_cache(url, result)
                        return result
                    
                    if b"%PDF-" in chunk:
                        result = {"valid": True, "url": final_url, "content_type": content_type}
                        _save_to_cache(url, result)
                        return result
                    else:
                        result = {"valid": False, "url": final_url, "reason": "invalid_magic_bytes"}
                        _save_to_cache(url, result)
                        return result

        except httpx.TimeoutException:
            result = {"valid": False, "url": url, "reason": "timeout"}
            _save_to_cache(url, result)
            return result
        except httpx.RequestError as exc:
            result = {"valid": False, "url": url, "reason": f"request_error_{type(exc).__name__}"}
            _save_to_cache(url, result)
            return result
        except Exception as exc:
            logger.error("Unexpected error validating PDF %s: %s", url, exc)
            result = {"valid": False, "url": url, "reason": "internal_error"}
            _save_to_cache(url, result)
            return result

    async def find_valid_pdf(self, candidates: List[str]) -> Optional[str]:
        """
        Takes a list of candidate URLs and returns the first one that is a valid PDF.
        Returns None if no candidates are valid.
        """
        for url in candidates:
            if not url:
                continue
            res = await self.validate_pdf_url(url)
            if res.get("valid"):
                return res.get("url")
        return None

pdf_validator = PDFValidator()
