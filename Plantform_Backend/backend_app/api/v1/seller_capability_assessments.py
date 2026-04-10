from fastapi import APIRouter, Depends, HTTPException, status

from backend_app.api.deps import get_capability_assessment_service
from backend_app.api.security import get_current_user
from backend_app.schemas.capability_assessment import CapabilityAssessmentCreateRequest, CapabilityAssessmentRead
from backend_app.services.capability_assessment_service import CapabilityAssessmentService
from backend_app.storage.memory_store import UserRecord

router = APIRouter(prefix="/seller", tags=["seller-capability-assessment"])


def get_seller_or_admin(user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if user.role not in {"seller", "platform_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller access required.")
    return user


@router.post("/capability-assessments", response_model=CapabilityAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_capability_assessment(
    payload: CapabilityAssessmentCreateRequest,
    user: UserRecord = Depends(get_seller_or_admin),
    service: CapabilityAssessmentService = Depends(get_capability_assessment_service),
) -> CapabilityAssessmentRead:
    try:
        return service.create_assessment(user.id, user.role, payload)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND
        if "ambiguous" in detail.lower():
            status_code = status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=detail) from exc
