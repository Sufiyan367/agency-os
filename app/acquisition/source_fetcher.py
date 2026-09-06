import time
import hashlib
import re
from typing import Optional, Dict, Any, Tuple, List
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

from app.core.security import is_safe_url, normalize_domain
from app.core.logging import logger

DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_REDIRECTS = 3

class FetchedSourceResult:
    """
    Standardized, transparent result of a safely fetched public source.
    Records provenance, status, normalized text, and content hash.
    """
    def __init__(
        self,
        source_url: str,
        final_url: str,
        source_domain: str,
        http_status: int,
        is_success: bool,
        retrieved_at: float,
        load_time_ms: float,
        content_hash: Optional[str] = None,
        raw_text: str = "",
        headers: Optional[Dict[str, str]] = None,
        error_message: Optional[str] = None,
        title: Optional[str] = None,
        emails_found: Optional[List[str]] = None,
        phones_found: Optional[List[str]] = None
    ):
        self.source_url = source_url
        self.final_url = final_url
        self.source_domain = source_domain
        self.http_status = http_status
        self.is_success = is_success
        self.retrieved_at = retrieved_at
        self.load_time_ms = load_time_ms
        self.content_hash = content_hash
        self.raw_text = raw_text
        self.headers = headers or {}
        self.error_message = error_message
        self.title = title
        self.emails_found = emails_found or []
        self.phones_found = phones_found or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_url": self.source_url,
            "final_url": self.final_url,
            "source_domain": self.source_domain,
            "http_status": self.http_status,
            "is_success": self.is_success,
            "retrieved_at": self.retrieved_at,
            "load_time_ms": self.load_time_ms,
            "content_hash": self.content_hash,
            "title": self.title,
            "error_message": self.error_message,
            "emails_found": self.emails_found,
            "phones_found": self.phones_found
        }

class SafeSourceFetcher:
    """
    Production-grade, resilient public webpage fetcher with strict SSRF defense,
    redirect hop validation, timeout controls, content hashing, and text extraction.
    """

    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")

    async def fetch(self, url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> FetchedSourceResult:
        start_time = time.perf_counter()
        now = time.time()

        if not url or not isinstance(url, str):
            return FetchedSourceResult(
                source_url=str(url),
                final_url=str(url),
                source_domain="",
                http_status=400,
                is_success=False,
                retrieved_at=now,
                load_time_ms=0.0,
                error_message="Invalid or empty URL provided."
            )

        clean_url = url.strip()
        parsed = urlparse(clean_url)
        protocol = parsed.scheme.lower()

        # Enforce HTTP/HTTPS protocol
        if protocol not in ("http", "https"):
            return FetchedSourceResult(
                source_url=clean_url,
                final_url=clean_url,
                source_domain=parsed.netloc or "",
                http_status=400,
                is_success=False,
                retrieved_at=now,
                load_time_ms=0.0,
                error_message=f"Disallowed protocol '{protocol}'. Only HTTP and HTTPS are permitted."
            )

        # Enforce SSRF Defense on initial URL
        is_safe, reason = is_safe_url(clean_url)
        if not is_safe:
            logger.warning(f"[SafeSourceFetcher] SSRF guard blocked URL {clean_url}: {reason}")
            return FetchedSourceResult(
                source_url=clean_url,
                final_url=clean_url,
                source_domain=normalize_domain(clean_url),
                http_status=403,
                is_success=False,
                retrieved_at=now,
                load_time_ms=0.0,
                error_message=f"SSRF security restriction: {reason}"
            )

        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 (B2B Research)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        try:
            # We follow redirects manually up to MAX_REDIRECTS to verify each hop against SSRF
            current_url = clean_url
            final_resp = None
            redirect_count = 0

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=False) as client:
                while redirect_count <= MAX_REDIRECTS:
                    resp = await client.get(current_url, headers=req_headers)
                    if resp.is_redirect and "location" in resp.headers:
                        redirect_count += 1
                        location = resp.headers["location"]
                        # Resolve relative redirect
                        next_url = str(httpx.URL(current_url).join(location))
                        is_safe_next, next_reason = is_safe_url(next_url)
                        if not is_safe_next:
                            logger.warning(f"[SafeSourceFetcher] SSRF guard blocked redirect to {next_url}: {next_reason}")
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            return FetchedSourceResult(
                                source_url=clean_url,
                                final_url=next_url,
                                source_domain=normalize_domain(next_url),
                                http_status=403,
                                is_success=False,
                                retrieved_at=now,
                                load_time_ms=round(elapsed_ms, 2),
                                error_message=f"Redirect blocked by SSRF defense: {next_reason}"
                            )
                        current_url = next_url
                    else:
                        final_resp = resp
                        break

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            if not final_resp:
                return FetchedSourceResult(
                    source_url=clean_url,
                    final_url=current_url,
                    source_domain=normalize_domain(current_url),
                    http_status=504,
                    is_success=False,
                    retrieved_at=now,
                    load_time_ms=round(elapsed_ms, 2),
                    error_message=f"Exceeded maximum redirects ({MAX_REDIRECTS})."
                )

            status_code = final_resp.status_code
            domain = normalize_domain(str(final_resp.url)) or normalize_domain(clean_url)
            body_text = final_resp.text

            # Parse and extract readable text
            title = None
            extracted_text = ""
            emails: List[str] = []
            phones: List[str] = []

            if status_code == 200:
                soup = BeautifulSoup(body_text, "html.parser")
                # Remove script and style elements
                for script in soup(["script", "style", "noscript", "svg"]):
                    script.extract()
                
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()

                text = soup.get_text(separator=" ", strip=True)
                # Normalize excessive whitespaces
                extracted_text = re.sub(r"\s+", " ", text).strip()

                # Extract emails
                for match in self.EMAIL_PATTERN.finditer(extracted_text):
                    em = match.group(0).lower().strip(".,;")
                    if not any(ext in em for ext in [".png", ".jpg", ".webp", ".gif", "@example.", "@domain."]):
                        if em not in emails:
                            emails.append(em)

                # Extract phones from tel links first, then text
                for tel_link in soup.find_all("a", href=True):
                    href = tel_link["href"]
                    if href.startswith("tel:"):
                        raw_tel = href[4:].strip()
                        if len(raw_tel) >= 7 and raw_tel not in phones:
                            phones.append(raw_tel)

                if not phones:
                    for match in self.PHONE_PATTERN.finditer(extracted_text):
                        ph = match.group(0).strip()
                        if len(ph) >= 10 and ph not in phones:
                            phones.append(ph)

            # Compute content hash
            content_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest() if extracted_text else None

            is_success = (status_code == 200 and len(extracted_text) >= 20)

            return FetchedSourceResult(
                source_url=clean_url,
                final_url=str(final_resp.url),
                source_domain=domain,
                http_status=status_code,
                is_success=is_success,
                retrieved_at=now,
                load_time_ms=round(elapsed_ms, 2),
                content_hash=content_hash,
                raw_text=extracted_text,
                headers=dict(final_resp.headers),
                title=title,
                emails_found=emails,
                phones_found=phones,
                error_message=None if is_success else f"HTTP Status {status_code}"
            )

        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return FetchedSourceResult(
                source_url=clean_url,
                final_url=clean_url,
                source_domain=normalize_domain(clean_url),
                http_status=504,
                is_success=False,
                retrieved_at=now,
                load_time_ms=round(elapsed_ms, 2),
                error_message=f"Request timed out after {timeout}s."
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return FetchedSourceResult(
                source_url=clean_url,
                final_url=clean_url,
                source_domain=normalize_domain(clean_url),
                http_status=502,
                is_success=False,
                retrieved_at=now,
                load_time_ms=round(elapsed_ms, 2),
                error_message=f"Network error: {str(e)}"
            )

    def extract_relevant_excerpt(self, full_text: str, keywords: List[str], max_chars: int = 300) -> Optional[str]:
        """
        Locates the most relevant passage containing the claimed keywords.
        Returns a concise, verifiable excerpt with context.
        """
        if not full_text or not keywords:
            return None

        lower_text = full_text.lower()
        best_pos = -1

        for kw in keywords:
            pos = lower_text.find(kw.lower().strip())
            if pos != -1:
                best_pos = pos
                break

        if best_pos == -1:
            return None

        # Extract window around best position
        start = max(0, best_pos - 80)
        end = min(len(full_text), best_pos + max_chars)
        snippet = full_text[start:end].strip()

        if start > 0:
            snippet = "..." + snippet
        if end < len(full_text):
            snippet = snippet + "..."

        return snippet

safe_source_fetcher = SafeSourceFetcher()
