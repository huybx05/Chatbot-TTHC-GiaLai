from __future__ import annotations

import pytest
from backend.app.auth.router import AdminUserCreateRequest, AdminUserUpdateRequest
from pydantic import ValidationError


def test_admin_can_create_a_client_or_admin_account() -> None:
    payload = AdminUserCreateRequest(
        username="new.admin",
        password="mat-khau-test",
        role="admin",
    )

    assert payload.username == "new.admin"
    assert payload.role == "admin"
    assert payload.is_active is True


def test_admin_user_update_requires_at_least_one_change() -> None:
    with pytest.raises(ValidationError):
        AdminUserUpdateRequest()


def test_admin_user_update_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        AdminUserUpdateRequest(role="operator")


def test_admin_user_update_allows_username_change() -> None:
    payload = AdminUserUpdateRequest(username="ten-moi")

    assert payload.username == "ten-moi"
