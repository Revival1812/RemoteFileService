
from fastapi import Depends

from app.core.config import get_settings
from app.core.security import require_api_client
from app.db.session import get_session

SettingsDep = Depends(get_settings)
SessionDep = Depends(get_session)
ApiClientDep = Depends(require_api_client)

