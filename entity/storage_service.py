from dataclasses import dataclass
from django.conf import settings


@dataclass
class StoredFileResult:
    backend: str
    file_id: str | None
    file_url: str | None
    local_field_value: object | None = None


class BaseStorageService:
    def save_file(self, uploaded_file):
        raise NotImplementedError

    def delete_file(self, entity):
        pass


class LocalStorageService(BaseStorageService):
    def save_file(self, uploaded_file):
        return StoredFileResult(
            backend="LOCAL",
            file_id=None,
            file_url=None,
            local_field_value=uploaded_file,
        )


class GoogleDriveStorageService(BaseStorageService):
    def _validate_config(self):
        if not settings.GDRIVE_ENABLED:
            raise RuntimeError("Google Drive storage is not enabled.")
        if not settings.GDRIVE_FOLDER_ID:
            raise RuntimeError("GDRIVE_FOLDER_ID is not configured.")

    def save_file(self, uploaded_file):
        self._validate_config()
        raise NotImplementedError("Google Drive upload is not implemented yet.")


def get_storage_service():
    backend = settings.FILE_STORAGE_BACKEND.upper()

    if backend == "GDRIVE":
        return GoogleDriveStorageService()

    return LocalStorageService()