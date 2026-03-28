from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.db.session import get_db
from app.models.users import User
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest
from app.services.profile_service import ProfileService, ProfileServiceError

router = APIRouter()
profile_service = ProfileService()


@router.get("/me/profile", response_model=ProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user)) -> ProfileResponse:
    return profile_service.to_profile_response(current_user)


@router.patch("/me/profile", response_model=ProfileResponse)
def update_my_profile(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    try:
        user = profile_service.update_profile(
            db=db,
            user=current_user,
            username=payload.username,
            email=payload.email,
            display_name=payload.display_name,
            gender=payload.gender,
            description=payload.description,
            fields_set=set(payload.model_fields_set),
        )
        return profile_service.to_profile_response(user)
    except ProfileServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me/avatar")
def get_my_avatar(current_user: User = Depends(get_current_user)) -> Response:
    payload = profile_service.get_avatar_payload(current_user)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no avatar")
    data, mime = payload
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def upload_my_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    file: UploadFile = File(...),
) -> Response:
    body = await file.read()
    try:
        profile_service.set_avatar(db=db, user=current_user, content=body)
    except ProfileServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    profile_service.clear_avatar(db=db, user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
