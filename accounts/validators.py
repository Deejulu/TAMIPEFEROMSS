"""
Custom password validators for accounts app.

These validators enforce character composition requirements that Django's
built-in validators do not cover: uppercase letters, lowercase letters,
and digits. They follow Django's validator API pattern.
"""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class UppercaseValidator:
    """
    Validates that the password contains at least one uppercase letter.
    """

    def validate(self, password, user=None):
        if not re.search(r"[A-Z]", password):
            raise ValidationError(
                _("This password must contain at least one uppercase letter (A-Z)."),
                code="password_no_upper",
            )

    def get_help_text(self):
        return _("Your password must contain at least one uppercase letter (A-Z).")


class LowercaseValidator:
    """
    Validates that the password contains at least one lowercase letter.
    """

    def validate(self, password, user=None):
        if not re.search(r"[a-z]", password):
            raise ValidationError(
                _("This password must contain at least one lowercase letter (a-z)."),
                code="password_no_lower",
            )

    def get_help_text(self):
        return _("Your password must contain at least one lowercase letter (a-z).")


class DigitValidator:
    """
    Validates that the password contains at least one digit.
    """

    def validate(self, password, user=None):
        if not re.search(r"[0-9]", password):
            raise ValidationError(
                _("This password must contain at least one digit (0-9)."),
                code="password_no_digit",
            )

    def get_help_text(self):
        return _("Your password must contain at least one digit (0-9).")
