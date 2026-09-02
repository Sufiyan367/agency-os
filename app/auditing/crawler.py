import time
from typing import Tuple, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from app.core.security import is_safe_url
from app.core.rate_limiter import default_rate_limiter
from app.core.logging import logger

FALLBACK_ERROR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Website Unavailable</title>
</head>
<body>
    <h1>Server Connection Error</h1>
    <p>The target web server failed to return a valid HTTP response or connection timed out.</p>
</body>
</html>
"""

class CrawlResult:
    def __init__(
        self,
        url: str,
        status_code: int,
        load_time_ms: float,
        headers: Dict[str, str],
        html_content: str,
        soup: BeautifulSoup,
        is_mock: bool = False,
        error_msg: Optional[str] = None
    ):
        self.url = url
        self.status_code = status_code
        self.load_time_ms = load_time_ms
        self.headers = headers
        self.html_content = html_content
        self.soup = soup
        self.is_mock = is_mock
        self.error_msg = error_msg

class ResilientWebsiteCrawler:
    """
    Safely crawls target websites with SSRF defense, rate limiting,
    automatic redirects, header inspection, and resilient network error handling.
    """
    async def fetch(self, url: str) -> CrawlResult:
        safe, msg = is_safe_url(url)
        if not safe:
            logger.warning(f"SSRF / Safety guard prevented crawling {url}: {msg}.")
            soup = BeautifulSoup(FALLBACK_ERROR_HTML, "html.parser")
            return CrawlResult(url, 403, 0.0, {}, FALLBACK_ERROR_HTML, soup, error_msg=msg)

        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        await default_rate_limiter.acquire()
        start_time = time.perf_counter()
        
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, verify=False) as client:
                resp = await client.get(url, headers=req_headers)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                soup = BeautifulSoup(resp.text, "html.parser")
                return CrawlResult(
                    url=str(resp.url),
                    status_code=resp.status_code,
                    load_time_ms=round(elapsed_ms, 2),
                    headers=dict(resp.headers),
                    html_content=resp.text,
                    soup=soup,
                    is_mock=False
                )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info(f"Direct HTTP fetch for {url} returned: {e}. Recording actual connectivity failure.")
            soup = BeautifulSoup(FALLBACK_ERROR_HTML, "html.parser")
            return CrawlResult(
                url=url,
                status_code=504,
                load_time_ms=round(elapsed_ms, 2),
                headers={},
                html_content=FALLBACK_ERROR_HTML,
                soup=soup,
                is_mock=False,
                error_msg=str(e)
            )

website_crawler = ResilientWebsiteCrawler()
