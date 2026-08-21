"""
Utility functions for the accounts app.

This module provides reusable helper functions for user management,
including automatic username generation with collision detection,
and profile photo processing.
"""

import re
import secrets
import unicodedata
from datetime import datetime
from io import BytesIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


# ---------------------------------------------------------------------------
# Username generation
# ---------------------------------------------------------------------------
# Every new account's username follows the single canonical pattern:
#
#     <FullNameNoSpaces><Year>TIF<RandomAccountID>
#     e.g. DavidOkonkwo2026TIF4K9X
#
# The trailing segment is a cryptographically random alphanumeric ID (via
# `secrets`), NOT a sequential counter, so usernames cannot be guessed or
# enumerated. The ID is also stored on the user as `account_id`.
#
# Ambiguous characters (0/O, 1/I/L) are excluded so the ID is safe for a
# human to read off the downloaded credentials file and retype.
ACCOUNT_ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
ACCOUNT_ID_LENGTH = 4
ACCOUNT_ID_MAX_LENGTH = 16
USERNAME_MARKER = "TIF"

# Matches the random ID at the end of a canonical generated username.
_ACCOUNT_ID_RE = re.compile(
    rf"^.*\d{{4}}{USERNAME_MARKER}(?P<account_id>[{ACCOUNT_ID_ALPHABET}]+)$"
)


def generate_account_id(length: int = ACCOUNT_ID_LENGTH) -> str:
    """
    Generate a cryptographically random alphanumeric account ID.

    Uses `secrets.choice` (not `random`) so the value is not predictable.

    Args:
        length: Number of characters to generate.

    Returns:
        A random uppercase alphanumeric string, e.g. "4K9X".
    """
    return "".join(secrets.choice(ACCOUNT_ID_ALPHABET) for _ in range(length))


def normalize_username_base(first_name: str, last_name: str) -> str:
    """
    Build the name portion of a username: unicode-normalized, ASCII-only,
    with all spaces and special characters removed.

    Falls back to "User" when no usable characters remain.
    """
    base = f"{first_name} {last_name}".strip()
    base = unicodedata.normalize("NFKD", base)
    base = base.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"\s+", "", base)  # Remove all spaces
    base = re.sub(r"[^a-zA-Z0-9]", "", base)  # Remove special characters
    return base or "User"


def build_username_prefix(first_name: str, last_name: str, year: int = None) -> str:
    """
    Build the non-random portion of a username: name + year + "TIF".

    Example: David Okonkwo, 2026 -> "DavidOkonkwo2026TIF"
    """
    if year is None:
        year = datetime.now().year
    return f"{normalize_username_base(first_name, last_name)}{year}{USERNAME_MARKER}"


def split_full_name(full_name: str) -> tuple:
    """
    Split a full name into (first_name, last_name).

    The first whitespace-separated word is the first name; everything after
    it is the last name. Used so that every account-creation path derives
    name parts identically.
    """
    parts = (full_name or "").strip().split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def extract_account_id(username: str) -> str:
    """
    Extract the random account ID from a canonical generated username.

    Returns an empty string for usernames that do not follow the
    <Name><Year>TIF<RandomID> pattern (e.g. legacy sequential usernames or
    usernames chosen explicitly by an administrator).
    """
    match = _ACCOUNT_ID_RE.match(username or "")
    return match.group("account_id") if match else ""


def generate_unique_username_with_id(
    first_name: str, last_name: str, year: int = None
) -> tuple:
    """
    Generate a unique username and its random account ID.

    Format: <FullNameNoSpaces><Year>TIF<RandomAccountID>
    Example: David Okonkwo, 2026 -> ("DavidOkonkwo2026TIF4K9X", "4K9X")

    Uniqueness is guaranteed: the username is checked against the database
    and a fresh random ID is generated on collision. If a run of collisions
    somehow exhausts the attempt budget, the random segment is widened
    rather than raising or falling back to a predictable value.

    Args:
        first_name: The user's first name.
        last_name: The user's last name.
        year: The registration year (defaults to current year).

    Returns:
        A (username, account_id) tuple.
    """
    UserModel = get_user_model()
    prefix = build_username_prefix(first_name, last_name, year)

    attempts_per_length = 100
    length = ACCOUNT_ID_LENGTH

    while length <= ACCOUNT_ID_MAX_LENGTH:
        for _attempt in range(attempts_per_length):
            account_id = generate_account_id(length)
            username = f"{prefix}{account_id}"
            if not UserModel.objects.filter(username=username).exists():
                return username, account_id
        # Astronomically unlikely: widen the random segment and keep trying
        # instead of crashing or emitting a guessable value.
        length += 1

    raise RuntimeError(
        "Unable to generate a unique username for "
        f"prefix {prefix!r} after exhausting the random ID space."
    )


def generate_unique_username(first_name: str, last_name: str, year: int = None) -> str:
    """
    Generate a unique username from a user's first and last name.

    Thin wrapper around :func:`generate_unique_username_with_id` for callers
    that only need the username. Prefer the `_with_id` variant when creating
    an account so the `account_id` field can be populated too.

    Example: David Okonkwo, 2026 -> DavidOkonkwo2026TIF4K9X
    """
    username, _account_id = generate_unique_username_with_id(
        first_name, last_name, year
    )
    return username


def process_profile_photo(uploaded_file):
    """
    Process an uploaded profile photo:
    - Resize to max 500x500 while maintaining aspect ratio
    - Crop to square from center
    - Convert to RGB for JPEG compatibility
    - Optimize and compress
    
    Returns a ContentFile with the processed image, or the original file
    if Pillow is not available or processing fails.
    """
    if not HAS_PILLOW:
        return uploaded_file

    try:
        image = Image.open(uploaded_file)
        
        # Convert to RGB if necessary (e.g., RGBA -> RGB for JPEG)
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Get current dimensions
        width, height = image.size
        
        # Crop to square from center
        min_dim = min(width, height)
        left = (width - min_dim) / 2
        top = (height - min_dim) / 2
        right = (width + min_dim) / 2
        bottom = (height + min_dim) / 2
        image = image.crop((left, top, right, bottom))
        
        # Resize to max 500x500
        image = image.resize((500, 500), Image.Resampling.LANCZOS)
        
        # Save to BytesIO
        output = BytesIO()
        
        # Determine format
        original_name = uploaded_file.name.lower()
        if original_name.endswith('.png'):
            image.save(output, format='PNG', optimize=True)
            content_type = 'image/png'
            extension = '.png'
        elif original_name.endswith('.gif'):
            # For GIF, we keep it as is if it's animated, otherwise convert to PNG
            image.save(output, format='PNG', optimize=True)
            content_type = 'image/png'
            extension = '.png'
        elif original_name.endswith('.webp'):
            image.save(output, format='WEBP', quality=85)
            content_type = 'image/webp'
            extension = '.webp'
        else:
            # Default to JPEG
            image.save(output, format='JPEG', quality=85, optimize=True)
            content_type = 'image/jpeg'
            extension = '.jpg'
        
        output.seek(0)
        
        # Create new filename with processed extension
        new_name = uploaded_file.name
        if '.' in new_name:
            new_name = new_name.rsplit('.', 1)[0] + extension
        else:
            new_name = new_name + extension
        
        return ContentFile(output.read(), name=new_name)
    
    except Exception:
        # If anything goes wrong, return the original file
        return uploaded_file


def optimize_image(uploaded_file, max_size=(1200, 1200), quality=85, format=None):
    """
    Generic image optimization for web use.
    
    - Resizes to max dimensions while maintaining aspect ratio
    - Optimizes and compresses
    - Preserves original format unless overridden
    
    Returns a ContentFile with the optimized image, or the original file
    if Pillow is not available or processing fails.
    """
    if not HAS_PILLOW:
        return uploaded_file

    try:
        image = Image.open(uploaded_file)
        
        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize if larger than max_size
        width, height = image.size
        max_width, max_height = max_size
        
        if width > max_width or height > max_height:
            ratio = min(max_width / width, max_height / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Save to BytesIO
        output = BytesIO()
        
        # Determine format
        original_name = uploaded_file.name.lower()
        if format:
            save_format = format.upper()
            extension = f'.{format.lower()}'
            content_type = f'image/{format.lower()}'
        elif original_name.endswith('.png'):
            save_format = 'PNG'
            extension = '.png'
            content_type = 'image/png'
        elif original_name.endswith('.webp'):
            save_format = 'WEBP'
            extension = '.webp'
            content_type = 'image/webp'
        elif original_name.endswith('.gif'):
            save_format = 'PNG'
            extension = '.png'
            content_type = 'image/png'
        else:
            save_format = 'JPEG'
            extension = '.jpg'
            content_type = 'image/jpeg'
        
        if save_format == 'JPEG':
            image.save(output, format='JPEG', quality=quality, optimize=True)
        elif save_format == 'WEBP':
            image.save(output, format='WEBP', quality=quality)
        else:
            image.save(output, format=save_format, optimize=True)
        
        output.seek(0)
        
        # Create new filename
        new_name = uploaded_file.name
        if '.' in new_name:
            new_name = new_name.rsplit('.', 1)[0] + extension
        else:
            new_name = new_name + extension
        
        return ContentFile(output.read(), name=new_name)
    
    except Exception:
        return uploaded_file
