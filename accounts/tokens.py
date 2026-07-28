"""
Token generation and verification for email verification.

Uses Django's TimestampSigner to create self-contained,
time-limited verification tokens that require no database storage.
"""

from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.utils.encoding import force_str
from django.urls import reverse

signer = TimestampSigner()

VERIFICATION_MAX_AGE = 86400  # 24 hours in seconds


def generate_verification_token(user):
    """
    Generate a signed, time-stamped token for email verification.

    The token encodes the user's primary key, ensuring that
    only the intended user can verify their email.

    Args:
        user: The CustomUser instance to generate a token for.

    Returns:
        A signed token string.
    """
    return signer.sign(str(user.pk))


def verify_token(token, max_age=VERIFICATION_MAX_AGE):
    """
    Verify a signed timestamp token and extract the user ID.

    Args:
        token: The signed token string to verify.
        max_age: Maximum age of the token in seconds (default: 24 hours).

    Returns:
        The unsigned value (user PK as string) if valid.

    Raises:
        SignatureExpired: If the token is older than max_age.
        BadSignature: If the token is invalid or tampered with.
    """
    try:
        return signer.unsign(token, max_age=max_age)
    except SignatureExpired:
        raise
    except BadSignature:
        raise


def build_verification_url(request, user):
    """
    Build the full verification URL for a user.

    Args:
        request: The current request (for building absolute URL).
        user: The user to generate the link for.

    Returns:
        A full absolute URL string.
    """
    token = generate_verification_token(user)
    return request.build_absolute_uri(
        reverse("accounts:verify_email", kwargs={"token": token})
    )
