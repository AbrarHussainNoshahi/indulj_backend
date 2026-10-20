import io
import os
import logging
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)


def enhance_uploaded_image(image_file, target_min_dim=1200, max_dim=1920, quality=92):
    """
    HD Image Processing Pipeline (Option C):
    - Corrects EXIF rotation for phone/camera uploads.
    - Upscales low-res/blurry photos to crisp HD (>= target_min_dim px) using high-order Lanczos resampling.
    - Gently downscales oversized images (beyond max_dim px) to prevent storage and loading lag while preserving detail.
    - Applies an UnsharpMask filter to restore edge acutance and eliminate camera/compression softness.
    - Applies a fine sharpness enhancement (+20%) to bring out food/text textures.
    - Micro-tunes contrast (+8%) and color vibrancy (+10%) for appetizing, rich food photos.
    - Encodes as high-quality JPEG with 4:4:4 chroma subsampling (no chroma blur).
    """
    if not image_file:
        return image_file

    try:
        # Seek to start and read bytes
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        img_bytes = image_file.read() if hasattr(image_file, "read") else None
        if hasattr(image_file, "seek"):
            image_file.seek(0)

        if not img_bytes:
            return image_file

        img = Image.open(io.BytesIO(img_bytes))

        # 1. EXIF auto-rotation (prevents sideways phone photos)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # 2. Convert transparent/palette images to clean RGB with white background
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(
                img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None
            )
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        orig_w, orig_h = img.size
        longest = max(orig_w, orig_h)

        # 3. Smart Lanczos Resampling
        # If low-res (e.g. 400x300, 600x400), upscale to HD so it never looks stretched/blurry
        if longest < target_min_dim:
            scale = target_min_dim / float(longest)
            new_w = int(round(orig_w * scale))
            new_h = int(round(orig_h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        elif longest > max_dim:
            scale = max_dim / float(longest)
            new_w = int(round(orig_w * scale))
            new_h = int(round(orig_h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 4. De-blurring: Unsharp Mask Filter
        # Radius 1.8, percent 140, threshold 2 sharpens micro-textures without grain
        img = img.filter(ImageFilter.UnsharpMask(radius=1.8, percent=140, threshold=2))

        # 5. Fine sharpness enhancement
        sharpener = ImageEnhance.Sharpness(img)
        img = sharpener.enhance(1.20)

        # 6. Micro-contrast & Color boost for crisp, vibrant food presentation
        contrast = ImageEnhance.Contrast(img)
        img = contrast.enhance(1.08)

        color = ImageEnhance.Color(img)
        img = color.enhance(1.10)

        # 7. Output to memory buffer
        output_io = io.BytesIO()
        img.save(
            output_io,
            format="JPEG",
            quality=quality,
            optimize=True,
            subsampling=0,  # 4:4:4 no chroma subsampling for crisp edges
        )
        output_io.seek(0)

        orig_name = getattr(image_file, "name", "image.jpg") or "image.jpg"
        base_name, _ = os.path.splitext(orig_name)
        new_name = f"{base_name}.jpg"

        return ContentFile(output_io.getvalue(), name=new_name)

    except Exception as e:
        logger.warning(f"HD image enhancement fallback: {e}")
        if hasattr(image_file, "seek"):
            image_file.seek(0)
        return image_file
