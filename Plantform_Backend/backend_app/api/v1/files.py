from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from backend_app.api.deps import get_file_service
from backend_app.core.config import get_settings
from backend_app.schemas.files import FileItemRead, FileListRead
from backend_app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/", response_model=FileListRead)
def list_downloadable_files(service: FileService = Depends(get_file_service)) -> FileListRead:
    settings = get_settings()
    items = [FileItemRead(**item) for item in service.list_files()]
    return FileListRead(
        items=items,
        total=len(items),
        download_root=str(settings.download_root),
    )


@router.get("/download/{relative_path:path}")
def download_file(relative_path: str, service: FileService = Depends(get_file_service)):
    resolved = service.resolve_file(relative_path)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    return FileResponse(
        path=resolved,
        filename=Path(relative_path).name,
        media_type="application/octet-stream",
    )
