import time
import ssl
import urllib.parse
from typing import Tuple, Dict, Any, Optional
import httpx
import httpcore
import httpcore._backends.anyio
from bs4 import BeautifulSoup
from app.core.security import is_safe_url, resolve_and_validate_hostname
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

MAX_REDIRECTS = 5

class SafeNetworkBackend(httpcore._backends.anyio.AnyIOBackend):
    """
    Custom transport backend for httpcore that eliminates DNS rebinding
    and enforces strict SSRF checks at the TCP connection boundary.
    """
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options = None,
    ):
        safe, ips, reason = resolve_and_validate_hostname(host)
        if not safe or not ips:
            raise httpcore.ConnectError(f"SSRF guard rejected connection to '{host}': {reason}")

        # Connect directly to the validated IP to prevent DNS rebinding.
        # SNI and TLS certificate verification will still use server_hostname=host.
        target_ip = ips[0]
        return await super().connect_tcp(
            host=target_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options
        )


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
        error_msg: Optional[str] = None,
        is_successful: bool = True
    ):
        self.url = url
        self.status_code = status_code
        self.load_time_ms = load_time_ms
        self.headers = headers
        self.html_content = html_content
        self.soup = soup
        self.is_mock = is_mock
        self.error_msg = error_msg
        self.is_successful = is_successful


class ResilientWebsiteCrawler:
    """
    Safely crawls target websites with SSRF defense, rate limiting,
    bounded manual redirects, TLS certificate validation, header inspection,
    and resilient network error handling.
    """
    async def fetch(self, url: str) -> CrawlResult:
        safe, msg = is_safe_url(url)
        if not safe:
            logger.warning(f"SSRF / Safety guard prevented crawling {url}: {msg}.")
            soup = BeautifulSoup(FALLBACK_ERROR_HTML, "html.parser")
            return CrawlResult(url, 403, 0.0, {}, FALLBACK_ERROR_HTML, soup, error_msg=f"SSRF Guard: {msg}", is_successful=False)

        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        await default_rate_limiter.acquire()
        start_time = time.perf_counter()

        pool = httpcore.AsyncConnectionPool(network_backend=SafeNetworkBackend())
        transport = httpx.AsyncHTTPTransport(verify=True)
        transport._pool = pool

        current_url = url
        redirect_count = 0
        final_resp = None
        soup = BeautifulSoup(FALLBACK_ERROR_HTML, "html.parser")

        try:
            async with httpx.AsyncClient(transport=transport, timeout=12.0, follow_redirects=False) as client:
                while True:
                    # Validate URL before every fetch (including every redirect hop)
                    is_safe, reason = is_safe_url(current_url)
                    if not is_safe:
                        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                        logger.warning(f"SSRF / Safety guard blocked redirect destination {current_url}: {reason}")
                        return CrawlResult(
                            url=current_url,
                            status_code=403,
                            load_time_ms=round(elapsed_ms, 2),
                            headers={},
                            html_content=FALLBACK_ERROR_HTML,
                            soup=soup,
                            is_mock=False,
                            error_msg=f"SSRF violation on redirect: {reason}",
                            is_successful=False
                        )

                    resp = await client.get(current_url, headers=req_headers)
                    final_resp = resp

                    if resp.is_redirect:
                        redirect_count += 1
                        if redirect_count > MAX_REDIRECTS:
                            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                            logger.warning(f"Crawl aborted for {url}: exceeded maximum redirect limit ({MAX_REDIRECTS}).")
                            return CrawlResult(
                                url=current_url,
                                status_code=310,
                                load_time_ms=round(elapsed_ms, 2),
                                headers=dict(resp.headers),
                                html_content=FALLBACK_ERROR_HTML,
                                soup=soup,
                                is_mock=False,
                                error_msg=f"Exceeded maximum redirect limit ({MAX_REDIRECTS})",
                                is_successful=False
                            )

                        location = resp.headers.get("Location")
                        if not location:
                            # 3xx without Location header
                            break
                        current_url = urllib.parse.urljoin(current_url, location)
                        continue
                    else:
                        break

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                soup = BeautifulSoup(final_resp.text, "html.parser")
                is_ok = 200 <= final_resp.status_code < 400
                return CrawlResult(
                    url=str(final_resp.url),
                    status_code=final_resp.status_code,
                    load_time_ms=round(elapsed_ms, 2),
                    headers=dict(final_resp.headers),
                    html_content=final_resp.text,
                    soup=soup,
                    is_mock=False,
                    is_successful=is_ok,
                    error_msg=None if is_ok else f"HTTP {final_resp.status_code}"
                )

        except (ssl.SSLCertVerificationError, ssl.SSLError) as ssl_err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info(f"TLS certificate verification failed for {current_url}: {ssl_err}. Recording as audit fact.")
            return CrawlResult(
                url=current_url,
                status_code=526,
                load_time_ms=round(elapsed_ms, 2),
                headers={},
                html_content=FALLBACK_ERROR_HTML,
                soup=soup,
                is_mock=False,
                error_msg="SSL/TLS Certificate Verification Failed",
                is_successful=False
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            err_str = str(e)
            if (
                "certificate verify failed" in err_str.lower()
                or "sslcertverificationerror" in err_str.lower()
                or "sslcertaverificationerror" in err_str.lower()
                or "tlscertificate" in err_str.lower()
                or ("ssl" in err_str.lower() and "verify" in err_str.lower())
                or ("tls" in err_str.lower() and "certificate" in err_str.lower())
            ):
                logger.info(f"TLS certificate verification error for {current_url}: {err_str}. Recording as audit fact.")
                return CrawlResult(
                    url=current_url,
                    status_code=526,
                    load_time_ms=round(elapsed_ms, 2),
                    headers={},
                    html_content=FALLBACK_ERROR_HTML,
                    soup=soup,
                    is_mock=False,
                    error_msg="SSL/TLS Certificate Verification Failed",
                    is_successful=False
                )
            if "ssrf" in err_str.lower() or "restricted" in err_str.lower():
                logger.warning(f"SSRF security violation during fetch of {current_url}: {err_str}")
                return CrawlResult(
                    url=current_url,
                    status_code=403,
                    load_time_ms=round(elapsed_ms, 2),
                    headers={},
                    html_content=FALLBACK_ERROR_HTML,
                    soup=soup,
                    is_mock=False,
                    error_msg=err_str,
                    is_successful=False
                )

            logger.info(f"Direct HTTP fetch for {current_url} returned: {e}. Recording actual connectivity failure.")
            return CrawlResult(
                url=current_url,
                status_code=504,
                load_time_ms=round(elapsed_ms, 2),
                headers={},
                html_content=FALLBACK_ERROR_HTML,
                soup=soup,
                is_mock=False,
                error_msg=str(e),
                is_successful=False
            )

website_crawler = ResilientWebsiteCrawler()
