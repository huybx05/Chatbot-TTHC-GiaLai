"""Chuẩn hoá IP client và chỉ tin header proxy khi đúng nguồn.

``X-Forwarded-For`` do client tự đặt được. Nếu ứng dụng đọc thẳng header này,
kẻ tấn công có thể đổi IP để vượt rate limit. Module này chỉ đọc header khi
request đến từ một proxy nằm trong ``TRUSTED_PROXY_IPS`` (mặc định localhost,
tức Nginx trên cùng máy). Sau Cloudflare, thêm dải IP Cloudflare vào biến đó và
dùng ``CF-Connecting-IP``.
"""

from __future__ import annotations

import ipaddress
from ipaddress import IPv4Network, IPv6Network

from fastapi import Request

from backend.app.config import settings

Network = IPv4Network | IPv6Network


def _parse_networks(raw: str) -> list[Network]:
    networks: list[Network] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _peer_is_trusted(peer: str) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in _parse_networks(settings.trusted_proxy_ips))


def _valid_ip(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    # Một số proxy ghi kèm cổng: 1.2.3.4:5678 hoặc [2001:db8::1]:443.
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            value = value[1:end]
    elif value.count(":") == 1 and "." in value:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            value = host
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def client_ip(request: Request) -> str | None:
    """IP thật của client, hoặc ``None`` nếu không xác định được."""
    peer = request.client.host if request.client else ""
    peer_ip = _valid_ip(peer)
    if peer_ip is None:
        return None

    if not _peer_is_trusted(peer_ip):
        # Không tin header khi request không đến từ proxy đã cấu hình.
        return peer_ip

    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for"
    )
    if forwarded:
        candidate = _valid_ip(forwarded.split(",")[0])
        if candidate is not None:
            return candidate
    return peer_ip
