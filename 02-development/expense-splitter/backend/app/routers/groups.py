from fastapi import APIRouter, Depends, status

from .. import schemas
from ..security import get_current_user
from ..store import Store, get_store

router = APIRouter(tags=["groups"])


@router.get("/groups", response_model=list[schemas.Group])
def list_groups(
    current_user: schemas.User = Depends(get_current_user), store: Store = Depends(get_store)
) -> list[schemas.Group]:
    return store.groups_for_user(current_user.id)


@router.post("/groups", response_model=schemas.Group, status_code=status.HTTP_201_CREATED)
def create_group(
    body: schemas.CreateGroupRequest,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.Group:
    return store.create_group(current_user.id, body.name, body.description)


@router.get("/groups/{group_id}", response_model=schemas.Group)
def get_group(
    group_id: str,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.Group:
    return store.require_membership(group_id, current_user.id)


@router.patch("/groups/{group_id}", response_model=schemas.Group)
def rename_group(
    group_id: str,
    body: schemas.RenameGroupRequest,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.Group:
    return store.rename_group(group_id, current_user.id, body.name)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: str,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> None:
    store.delete_group(group_id, current_user.id)


@router.post("/groups/{group_id}/members", response_model=schemas.Group)
def add_member(
    group_id: str,
    body: schemas.AddMemberRequest,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.Group:
    return store.add_member(group_id, current_user.id, body.email)


@router.post("/groups/{group_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_group(
    group_id: str,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> None:
    store.leave_group(group_id, current_user.id)
