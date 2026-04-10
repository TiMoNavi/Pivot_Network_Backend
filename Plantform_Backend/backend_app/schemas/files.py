from pydantic import BaseModel, Field


class FileItemRead(BaseModel):
    name: str
    relative_path: str
    size_bytes: int


class FileListRead(BaseModel):
    items: list[FileItemRead] = Field(default_factory=list)
    total: int
    download_root: str
