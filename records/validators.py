from django.core.exceptions import ValidationError
from PIL import Image

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def check_image(file):
    """Validate size and REAL content (Pillow decodes the bytes). Returns the
    safe file extension. We never trust the filename or the Content-Type header."""
    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError("Image must be 5 MB or smaller.")
    try:
        img = Image.open(file)
        img.verify()          # checks the file is a well-formed image
        fmt = img.format
    except Exception:
        raise ValidationError("Upload a valid image file.")
    finally:
        file.seek(0)          # verify() consumed the stream; rewind for saving
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Only JPEG, PNG, or WebP images are allowed.")
    return ALLOWED_FORMATS[fmt]