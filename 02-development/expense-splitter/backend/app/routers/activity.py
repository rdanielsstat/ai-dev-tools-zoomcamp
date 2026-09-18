from fastapi import APIRouter, Depends

from .. import schemas
from ..security import get_current_user
from ..store import Store, get_store

router = APIRouter(tags=["activity"])


@router.get("/groups/{group_id}/activity", response_model=list[schemas.ActivityEvent])
def list_activity(
    group_id: str,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> list[schemas.ActivityEvent]:
    return store.list_activity(group_id, current_user.id)
