from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class DocumentFileSystemStorage(FileSystemStorage):
    """
    Dedicated storage that always saves documents (PDF menus, docs, etc.)
    directly to the local VPS server filesystem (MEDIA_ROOT), completely
    bypassing Cloudinary.
    """

    def __init__(self, location=None, base_url=None, *args, **kwargs):
        if location is None:
            location = str(settings.MEDIA_ROOT)
        if base_url is None:
            base_url = settings.MEDIA_URL
        super().__init__(location=location, base_url=base_url, *args, **kwargs)


document_storage = DocumentFileSystemStorage()
