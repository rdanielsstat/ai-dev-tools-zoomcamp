from datetime import date

from fastapi import APIRouter, Depends, Query, status

from .. import schemas
from ..security import get_current_user
from ..store import Store, get_store

router = APIRouter(tags=["expenses"])


@router.get("/groups/{group_id}/expenses", response_model=list[schemas.Expense])
def list_expenses(
    group_id: str,
    member_id: str | None = Query(default=None, alias="memberId"),
    category: str | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> list[schemas.Expense]:
    return store.list_expenses(
        group_id,
        current_user.id,
        member_id=member_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/groups/{group_id}/expenses", response_model=schemas.Expense, status_code=status.HTTP_201_CREATED)
def add_expense(
    group_id: str,
    body: schemas.NewExpenseInput,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.Expense:
    return store.add_expense(group_id, current_user.id, body)


@router.patch("/expenses/{expense_id}", response_model=schemas.Expense)
def edit_expense(
    expense_id: str,
    body: schemas.NewExpenseInput,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.Expense:
    return store.edit_expense(expense_id, current_user.id, body)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: str,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> None:
    store.delete_expense(expense_id, current_user.id)
