import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ApiClient:
    key_id: str
    is_admin: bool = False
    owner_id: str | None = None


def _constant_time_contains(candidate: str, values: list[str]) -> bool:
    found = False
    for value in values:
        found = secrets.compare_digest(candidate, value) or found
    return found


async def require_api_client(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> ApiClient:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    is_admin = _constant_time_contains(token, settings.admin_api_keys)
    is_valid = is_admin or _constant_time_contains(token, settings.api_keys)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    owner_id = request.headers.get("x-owner-id") or None
    return ApiClient(key_id=f"key:{secrets.token_hex(4)}", is_admin=is_admin, owner_id=owner_id)


async def optional_api_client(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ApiClient | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1]
    is_admin = _constant_time_contains(token, settings.admin_api_keys)
    is_valid = is_admin or _constant_time_contains(token, settings.api_keys)
    if not is_valid:
        return None
    return ApiClient(key_id=f"key:{secrets.token_hex(4)}", is_admin=is_admin)
