"""Crawler TTHC qua API công khai của Cổng Dịch vụ công Quốc gia.

Khác với hướng bóc text DOM: nguồn dữ liệu ở đây là JSON API có cấu trúc,
nên không cần trình duyệt (Playwright) và không có rác giao diện.
"""

API_LIST_PATH = "/api/v1/submitting/formality/list-all-public-formality-by-citizen"
API_DETAIL_PATH = "/api/v1/configuring/formality/get-formality-by-citizen"

TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
