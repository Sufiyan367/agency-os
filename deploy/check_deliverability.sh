#!/usr/bin/env bash
# ==============================================================================
# Agency OS: DNS Deliverability & Authentication Inspector (SPF, DKIM, DMARC)
# Language: Bash
# ==============================================================================

set -eo pipefail

DOMAIN="${1:-automatedagencyos.tech}"

echo "=================================================================="
echo "   AGENCY OS — DNS DELIVERABILITY AUDIT: $DOMAIN"
echo "=================================================================="
echo ""

# 1. Check MX records
echo "[1/4] Checking MX Records for $DOMAIN..."
if command -v dig >/dev/null 2>&1; then
    dig +short MX "$DOMAIN" || echo "  No MX records found"
else
    nslookup -type=MX "$DOMAIN" || true
fi
echo ""

# 2. Check SPF (TXT at apex)
echo "[2/4] Checking SPF Record for $DOMAIN..."
if command -v dig >/dev/null 2>&1; then
    dig +short TXT "$DOMAIN" | grep "v=spf1" || echo "  No SPF TXT record found"
else
    nslookup -type=TXT "$DOMAIN" || true
fi
echo ""

# 3. Check DMARC (TXT at _dmarc.domain)
echo "[3/4] Checking DMARC Record for _dmarc.$DOMAIN..."
if command -v dig >/dev/null 2>&1; then
    dig +short TXT "_dmarc.$DOMAIN" | grep "v=DMARC1" || echo "  No DMARC TXT record found"
else
    nslookup -type=TXT "_dmarc.$DOMAIN" || true
fi
echo ""

# 4. Check DKIM Selectors (default / google / titan)
echo "[4/4] Checking Common DKIM Selectors..."
for selector in default google titan mail s1; do
    echo "  Checking selector: $selector._domainkey.$DOMAIN"
    if command -v dig >/dev/null 2>&1; then
        res=$(dig +short TXT "$selector._domainkey.$DOMAIN" || true)
        if [ -n "$res" ]; then
            echo "    FOUND: $res"
        else
            echo "    (not found)"
        fi
    fi
done
echo ""
echo "=================================================================="
