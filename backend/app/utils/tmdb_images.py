TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"


def tmdb_image_url(image_path: str | None, size: str = "w500") -> str | None:
    if not image_path:
        return None
    return f"{TMDB_IMAGE_BASE_URL}/{size}{image_path}"
