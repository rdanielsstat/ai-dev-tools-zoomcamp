from fastapi import APIRouter, Depends, status

from .. import schemas
from ..security import get_bearer_token, get_current_user
from ..store import Store, get_store

router = APIRouter(tags=["auth"])


@router.post("/auth/signup", response_model=schemas.AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: schemas.SignupRequest, store: Store = Depends(get_store)) -> schemas.AuthResponse:
    user, token = store.sign_up(body.name, body.email, body.password)
    return schemas.AuthResponse(token=token, user=user)


@router.post("/auth/login", response_model=schemas.AuthResponse)
def login(body: schemas.LoginRequest, store: Store = Depends(get_store)) -> schemas.AuthResponse:
    user, token = store.log_in(body.email, body.password)
    return schemas.AuthResponse(token=token, user=user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(get_bearer_token),
    _: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> None:
    store.log_out(token)


@router.get("/me", response_model=schemas.User)
def get_me(current_user: schemas.User = Depends(get_current_user)) -> schemas.User:
    return current_user


@router.patch("/me", response_model=schemas.User)
def update_me(
    body: schemas.UpdateProfileRequest,
    current_user: schemas.User = Depends(get_current_user),
    store: Store = Depends(get_store),
) -> schemas.User:
    return store.update_profile(current_user.id, body.name, body.email)
