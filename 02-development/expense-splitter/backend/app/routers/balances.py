from fastapi import APIRouter, Depends, status

from .. import schemas
from ..security import get_current_user
from ..store import Store, get_store

router = APIRouter(tags=["balances"])


@router.get("/groups/{group_id}/balances", response_model=schemas.GroupBalances)
def get_balances(
    group_id: str,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.GroupBalances:
    return store.get_balances(group_id, current_user.id)


@router.get("/groups/{group_id}/payments", response_model=list[schemas.Payment])
def list_payments(
    group_id: str,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> list[schemas.Payment]:
    return store.list_payments(group_id, current_user.id)


@router.post("/groups/{group_id}/payments", response_model=schemas.Payment, status_code=status.HTTP_201_CREATED)
def record_payment(
    group_id: str,
    body: schemas.NewPaymentInput,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.Payment:
    return store.record_payment(group_id, current_user.id, body)
