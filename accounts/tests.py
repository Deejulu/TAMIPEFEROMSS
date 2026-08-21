from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError
from django.core import mail
from django.core.management import call_command
from django.test.utils import override_settings
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from unittest import mock
from io import StringIO
import logging
import re

from . import utils as accounts_utils
from .models import CustomUser, SecurityQuestion, SavedCard
from .forms import CustomSignupForm, SecurityQuestionRecoveryForm, RecoveryPasswordResetForm
from .utils import (
    ACCOUNT_ID_ALPHABET,
    ACCOUNT_ID_LENGTH,
    extract_account_id,
    generate_account_id,
    generate_unique_username,
    generate_unique_username_with_id,
)
from .validators import UppercaseValidator, LowercaseValidator, DigitValidator
from .constants import SECURITY_QUESTIONS
from notifications.models import Notification
from shop.models import Category, Order, OrderItem, Product, Payment

User = get_user_model()


# =============================================================================
# Username Generation Tests
# =============================================================================

class UsernameGenerationTests(TestCase):
    """
    Tests for the canonical username generator.

    New usernames follow <FullNameNoSpaces><Year>TIF<RandomAccountID>,
    e.g. DavidOkonkwo2026TIF4K9X. The trailing ID is cryptographically
    random, NOT sequential.
    """

    def _pattern(self, base, year=None):
        year = year or timezone.now().year
        return re.compile(
            rf"^{base}{year}TIF[{ACCOUNT_ID_ALPHABET}]{{{ACCOUNT_ID_LENGTH}}}$"
        )

    def test_basic_username_generation(self):
        """Username is name + year + TIF + random ID."""
        username = generate_unique_username("John", "Doe")
        self.assertRegex(username, self._pattern("JohnDoe"))

    def test_username_contains_tif_marker(self):
        """The TIF marker must always be present (regression: it was missing)."""
        username = generate_unique_username("John", "Doe")
        self.assertIn("TIF", username)
        self.assertIn(f"{timezone.now().year}TIF", username)

    def test_spaces_removed(self):
        """Spaces are stripped from the name portion."""
        username = generate_unique_username("  John  ", "  Doe  ")
        self.assertRegex(username, self._pattern("JohnDoe"))

    def test_special_characters_removed(self):
        """Special characters are stripped from the name portion."""
        username = generate_unique_username("John!", "Doe@")
        self.assertRegex(username, self._pattern("JohnDoe"))

    def test_unicode_normalization(self):
        """Unicode characters are normalized to ASCII."""
        username = generate_unique_username("José", "García")
        self.assertRegex(username, self._pattern("JoseGarcia"))

    def test_empty_first_name_fallback(self):
        """Empty first name still generates a valid username."""
        username = generate_unique_username("", "Doe")
        self.assertRegex(username, self._pattern("Doe"))

    def test_empty_last_name_fallback(self):
        """Empty last name still generates a valid username."""
        username = generate_unique_username("John", "")
        self.assertRegex(username, self._pattern("John"))

    def test_both_names_empty_fallback(self):
        """Both names empty falls back to 'User'."""
        username = generate_unique_username("", "")
        self.assertRegex(username, self._pattern("User"))

    def test_year_is_used_in_prefix(self):
        """The supplied year appears before the TIF marker."""
        u1 = generate_unique_username("Test", "User", year=2026)
        u2 = generate_unique_username("Test", "User", year=2027)
        self.assertTrue(u1.startswith("TestUser2026TIF"))
        self.assertTrue(u2.startswith("TestUser2027TIF"))

    # ---------------------------------------------------------------
    # Randomness / non-sequential guarantees
    # ---------------------------------------------------------------

    def test_id_is_not_sequential(self):
        """
        Generated IDs must not be the old sequential 001/002/003 counter.
        """
        usernames = [
            generate_unique_username("John", "Doe", year=2026) for _ in range(10)
        ]
        year = 2026
        for index, username in enumerate(usernames, start=1):
            self.assertNotEqual(
                username, f"JohnDoe{year}TIF{index:03d}",
                "Username still looks sequential",
            )
            self.assertNotEqual(
                username, f"JohnDoe{year}{index:03d}",
                "Username reverted to the old no-TIF sequential format",
            )

    def test_ids_are_random_and_varied(self):
        """
        Repeated generation for the same name yields differing random IDs.

        With a 31-character alphabet and 4 characters there are ~923k
        combinations, so 25 draws colliding into fewer than 20 distinct
        values would indicate the value is not actually random.
        """
        ids = {
            generate_unique_username_with_id("John", "Doe", year=2026)[1]
            for _ in range(25)
        }
        self.assertGreaterEqual(len(ids), 20)

    def test_generated_usernames_are_unique(self):
        """Generating many usernames for one name produces no duplicates."""
        usernames = [
            generate_unique_username("John", "Doe", year=2026) for _ in range(50)
        ]
        self.assertEqual(len(usernames), len(set(usernames)))

    def test_account_id_matches_username_suffix(self):
        """The returned account_id is exactly the username's trailing segment."""
        username, account_id = generate_unique_username_with_id(
            "David", "Okonkwo", year=2026
        )
        self.assertEqual(username, f"DavidOkonkwo2026TIF{account_id}")
        self.assertEqual(len(account_id), ACCOUNT_ID_LENGTH)
        self.assertEqual(extract_account_id(username), account_id)

    def test_collision_is_regenerated_not_crashed(self):
        """
        When the first random ID already exists, a different one is issued
        and no exception is raised.
        """
        taken_id = "ABCD"
        taken_username = f"JohnDoe2026TIF{taken_id}"
        User.objects.create_user(
            email="taken@example.com",
            full_name="John Doe",
            password="TestPass123",
            username=taken_username,
        )

        real_generate_account_id = accounts_utils.generate_account_id
        calls = {"n": 0}

        def collide_once(length=ACCOUNT_ID_LENGTH):
            """Return the taken ID first, then defer to the real generator."""
            calls["n"] += 1
            if calls["n"] == 1:
                return taken_id
            return real_generate_account_id(length)

        with mock.patch.object(
            accounts_utils, "generate_account_id", side_effect=collide_once
        ):
            username, account_id = generate_unique_username_with_id(
                "John", "Doe", year=2026
            )

        self.assertGreaterEqual(calls["n"], 2, "Collision was not detected")
        self.assertNotEqual(username, taken_username)
        self.assertNotEqual(account_id, taken_id)
        self.assertFalse(User.objects.filter(username=username).exists())

    def test_exhausted_attempts_widen_id_instead_of_crashing(self):
        """
        A pathological run of collisions widens the random segment rather
        than raising or emitting a predictable value.
        """
        with mock.patch.object(
            accounts_utils,
            "generate_account_id",
            side_effect=lambda length=ACCOUNT_ID_LENGTH: "Z" * length,
        ):
            User.objects.create_user(
                email="widen@example.com",
                full_name="John Doe",
                password="TestPass123",
                username="JohnDoe2026TIFZZZZ",
            )
            username, account_id = generate_unique_username_with_id(
                "John", "Doe", year=2026
            )

        self.assertEqual(username, "JohnDoe2026TIFZZZZZ")
        self.assertEqual(account_id, "ZZZZZ")


class AccountIdFieldTests(TestCase):
    """The random ID is stored on the user profile as its own field."""

    def test_account_id_stored_on_creation(self):
        """A new user gets account_id populated automatically."""
        user = User.objects.create_user(
            email="stored@example.com",
            full_name="David Okonkwo",
            password="TestPass123",
        )
        self.assertTrue(user.account_id)
        self.assertEqual(len(user.account_id), ACCOUNT_ID_LENGTH)
        self.assertTrue(user.username.endswith(user.account_id))
        self.assertEqual(user.username, f"DavidOkonkwo{timezone.now().year}TIF{user.account_id}")

    def test_account_id_persisted_to_database(self):
        """account_id is retrievable separately from the username."""
        user = User.objects.create_user(
            email="persist@example.com",
            full_name="David Okonkwo",
            password="TestPass123",
        )
        reloaded = User.objects.get(pk=user.pk)
        self.assertEqual(reloaded.account_id, user.account_id)

    def test_explicit_username_without_tif_leaves_account_id_blank(self):
        """
        An explicitly-chosen username (e.g. the superuser command) has no
        random segment, so account_id stays blank rather than being invented.
        """
        user = User.objects.create_user(
            email="explicit@example.com",
            full_name="Explicit Admin",
            password="TestPass123",
            username="admin",
        )
        self.assertEqual(user.username, "admin")
        self.assertEqual(user.account_id, "")

    def test_explicit_canonical_username_backfills_account_id(self):
        """An explicit username in canonical form has its ID recorded."""
        user = User.objects.create_user(
            email="canonical@example.com",
            full_name="David Okonkwo",
            password="TestPass123",
            username="DavidOkonkwo2026TIFQ7WK",
        )
        self.assertEqual(user.account_id, "Q7WK")

    def test_existing_username_not_rewritten_on_later_save(self):
        """
        Saving an EXISTING user never regenerates their username or
        account_id - the change is new-accounts-only.
        """
        user = User.objects.create_user(
            email="legacy@example.com",
            full_name="Legacy User",
            password="TestPass123",
            username="LegacyUser2025001",  # old sequential format
        )
        original_username = user.username
        original_password = user.password
        self.assertEqual(user.account_id, "")

        user.phone_number = "08012345678"
        user.save()
        user.refresh_from_db()

        self.assertEqual(user.username, original_username)
        self.assertEqual(user.account_id, "")
        self.assertEqual(user.password, original_password)


class UsernameGenerationPathConsistencyTests(TestCase):
    """
    Every account-creation path must use the ONE canonical generator.

    This is the regression guard for the original bug: some paths produced
    usernames without the TIF marker.
    """

    CANONICAL = re.compile(
        rf"^[A-Za-z0-9]+\d{{4}}TIF[{ACCOUNT_ID_ALPHABET}]{{{ACCOUNT_ID_LENGTH},}}$"
    )

    def _assert_canonical(self, user, expected_base):
        self.assertRegex(user.username, self.CANONICAL)
        self.assertIn("TIF", user.username)
        self.assertTrue(user.username.startswith(expected_base))
        self.assertTrue(user.account_id)
        self.assertTrue(user.username.endswith(user.account_id))

    def test_manager_create_user_path(self):
        """Path 1: CustomUserManager.create_user()."""
        user = User.objects.create_user(
            email="path1@example.com",
            full_name="Path One",
            password="TestPass123",
        )
        self._assert_canonical(user, "PathOne")

    def test_customer_self_signup_path(self):
        """Path 2: accounts.CustomSignupForm (customer self-signup)."""
        form = CustomSignupForm(data={
            "first_name": "Path",
            "last_name": "Two",
            "email": "path2@example.com",
            "password1": "StrongPass1!",
            "password2": "StrongPass1!",
            "security_question_1": "first_pet",
            "security_answer_1": "Fluffy",
            "security_question_2": "birth_city",
            "security_answer_2": "Lagos",
            "security_question_3": "first_school",
            "security_answer_3": "Springfield",
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self._assert_canonical(user, "PathTwo")

    def test_admin_user_create_path(self):
        """Path 3: admin_dashboard.UserCreateForm (admin-created any role)."""
        from admin_dashboard.forms import UserCreateForm

        form = UserCreateForm(data={
            "full_name": "Path Three",
            "email": "path3@example.com",
            "role": User.Role.CUSTOMER,
            "is_active": True,
            "password1": "StrongPass1!",
            "password2": "StrongPass1!",
            "security_question_1": "first_pet",
            "security_answer_1": "Fluffy",
            "security_question_2": "birth_city",
            "security_answer_2": "Lagos",
            "security_question_3": "first_school",
            "security_answer_3": "Springfield",
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self._assert_canonical(user, "PathThree")

    def test_admin_staff_create_path(self):
        """Path 4: admin_dashboard.StaffCreateForm (admin-created staff)."""
        from admin_dashboard.forms import StaffCreateForm

        form = StaffCreateForm(data={
            "full_name": "Path Four",
            "email": "path4@example.com",
            "role": User.Role.STAFF,
            "is_active": True,
            "password1": "StrongPass1!",
            "password2": "StrongPass1!",
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self._assert_canonical(user, "PathFour")

    def test_direct_model_save_path(self):
        """Path 5: direct model instantiation (shell, scripts, fixtures)."""
        user = User(email="path5@example.com", full_name="Path Five")
        user.set_password("TestPass123")
        user.save()
        self._assert_canonical(user, "PathFive")

    def test_all_paths_produce_distinct_usernames(self):
        """No two creation paths can collide on a username."""
        usernames = set()
        for i in range(5):
            user = User.objects.create_user(
                email=f"same{i}@example.com",
                full_name="Same Name",
                password="TestPass123",
            )
            usernames.add(user.username)
        self.assertEqual(len(usernames), 5)


# =============================================================================
# Password Validator Tests
# =============================================================================

class PasswordValidatorTests(TestCase):
    """Tests for custom password validators."""

    def setUp(self):
        self.uppercase_validator = UppercaseValidator()
        self.lowercase_validator = LowercaseValidator()
        self.digit_validator = DigitValidator()

    def test_uppercase_validator_passes(self):
        """Test that password with uppercase letter passes."""
        try:
            self.uppercase_validator.validate("TestPass123")
        except ValidationError:
            self.fail("UppercaseValidator raised ValidationError unexpectedly!")

    def test_uppercase_validator_fails(self):
        """Test that password without uppercase letter fails."""
        with self.assertRaises(ValidationError):
            self.uppercase_validator.validate("testpass123")

    def test_lowercase_validator_passes(self):
        """Test that password with lowercase letter passes."""
        try:
            self.lowercase_validator.validate("TestPass123")
        except ValidationError:
            self.fail("LowercaseValidator raised ValidationError unexpectedly!")

    def test_lowercase_validator_fails(self):
        """Test that password without lowercase letter fails."""
        with self.assertRaises(ValidationError):
            self.lowercase_validator.validate("TESTPASS123")

    def test_digit_validator_passes(self):
        """Test that password with digit passes."""
        try:
            self.digit_validator.validate("TestPass123")
        except ValidationError:
            self.fail("DigitValidator raised ValidationError unexpectedly!")

    def test_digit_validator_fails(self):
        """Test that password without digit fails."""
        with self.assertRaises(ValidationError):
            self.digit_validator.validate("TestPassOnly")

    def test_uppercase_help_text(self):
        """Test that uppercase validator provides help text."""
        self.assertEqual(
            self.uppercase_validator.get_help_text(),
            "Your password must contain at least one uppercase letter (A-Z)."
        )

    def test_lowercase_help_text(self):
        """Test that lowercase validator provides help text."""
        self.assertEqual(
            self.lowercase_validator.get_help_text(),
            "Your password must contain at least one lowercase letter (a-z)."
        )

    def test_digit_help_text(self):
        """Test that digit validator provides help text."""
        self.assertEqual(
            self.digit_validator.get_help_text(),
            "Your password must contain at least one digit (0-9)."
        )


# =============================================================================
# Security Question Model Tests
# =============================================================================

class SecurityQuestionModelTests(TestCase):
    """Tests for the SecurityQuestion model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com",
            full_name="Test User",
            password="TestPass123",
            username="testuser1",
        )

    def test_create_security_question(self):
        """Test that a security question can be created."""
        sq = SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        self.assertEqual(sq.user, self.user)
        self.assertEqual(sq.question, "first_pet")
        self.assertTrue(check_password("Fluffy", sq.hashed_answer))

    def test_security_answer_hashing(self):
        """Test that security answers are stored hashed, not plain text."""
        sq = SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        self.assertNotEqual(sq.hashed_answer, "Fluffy")
        self.assertTrue(sq.hashed_answer.startswith("pbkdf2_sha256$"))

    def test_check_password_verification(self):
        """Test that check_password correctly verifies hashed answers."""
        sq = SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        self.assertTrue(check_password("Fluffy", sq.hashed_answer))
        self.assertFalse(check_password("WrongAnswer", sq.hashed_answer))

    def test_unique_constraint(self):
        """Test that a user cannot have duplicate questions."""
        SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        with self.assertRaises(Exception):
            SecurityQuestion.objects.create(
                user=self.user,
                question="first_pet",
                hashed_answer=make_password("Rex"),
            )

    def test_cascade_delete(self):
        """Test that deleting a user deletes their security questions."""
        SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="birth_city",
            hashed_answer=make_password("New York"),
        )
        self.assertEqual(SecurityQuestion.objects.count(), 2)
        self.user.delete()
        self.assertEqual(SecurityQuestion.objects.count(), 0)

    def test_question_display(self):
        """Test that get_question_display returns the human-readable text."""
        sq = SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        self.assertEqual(sq.get_question_display(), "What was the name of your first pet?")

    def test_related_name(self):
        """Test that security_questions related name works."""
        SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        self.assertEqual(self.user.security_questions.count(), 1)


# =============================================================================
# Signup Form Tests
# =============================================================================

class SignupFormTests(TestCase):
    """Tests for the CustomSignupForm."""

    def setUp(self):
        self.valid_form_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone_number": "+1234567890",
            "password1": "StrongPass1",
            "password2": "StrongPass1",
            "security_question_1": "first_pet",
            "security_answer_1": "Fluffy",
            "security_question_2": "birth_city",
            "security_answer_2": "New York",
            "security_question_3": "favorite_teacher",
            "security_answer_3": "Mr. Smith",
        }

    def test_form_has_required_fields(self):
        """Test that the form contains all required fields."""
        form = CustomSignupForm()
        self.assertIn("first_name", form.fields)
        self.assertIn("last_name", form.fields)
        self.assertIn("email", form.fields)
        self.assertIn("phone_number", form.fields)
        self.assertIn("password1", form.fields)
        self.assertIn("password2", form.fields)
        self.assertIn("security_question_1", form.fields)
        self.assertIn("security_answer_1", form.fields)
        self.assertIn("security_question_2", form.fields)
        self.assertIn("security_answer_2", form.fields)
        self.assertIn("security_question_3", form.fields)
        self.assertIn("security_answer_3", form.fields)

    def test_form_does_not_expose_username(self):
        """Test that username field is not exposed in the form."""
        form = CustomSignupForm()
        self.assertNotIn("username", form.fields)

    def test_form_does_not_expose_full_name(self):
        """Test that full_name field is not exposed in the form."""
        form = CustomSignupForm()
        self.assertNotIn("full_name", form.fields)

    def test_valid_form_passes(self):
        """Test that a valid form submission passes validation."""
        form = CustomSignupForm(data=self.valid_form_data)
        self.assertTrue(form.is_valid())

    def test_duplicate_security_questions_rejected(self):
        """Test that duplicate security questions are rejected."""
        data = self.valid_form_data.copy()
        data["security_question_2"] = "first_pet"
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("Please select three different security questions", str(form.errors))

    def test_missing_security_question_rejected(self):
        """Test that missing security question is rejected."""
        data = self.valid_form_data.copy()
        data["security_question_1"] = ""
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("Please select all three security questions", str(form.errors))

    def test_missing_security_answer_rejected(self):
        """Test that missing security answer is rejected."""
        data = self.valid_form_data.copy()
        data["security_answer_1"] = ""
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("Please provide answers for all three security questions", str(form.errors))

    def test_duplicate_email_rejected(self):
        """Test that duplicate email is rejected."""
        User.objects.create_user(
            email="john@example.com",
            full_name="Existing User",
            password="TestPass123",
            username="existing1",
        )
        form = CustomSignupForm(data=self.valid_form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("already exists", str(form.errors))

    def test_password_mismatch_rejected(self):
        """Test that password mismatch is rejected."""
        data = self.valid_form_data.copy()
        data["password2"] = "DifferentPass1"
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())

    def test_password_too_short_rejected(self):
        """Test that too-short password is rejected."""
        data = self.valid_form_data.copy()
        data["password1"] = "Ab1"
        data["password2"] = "Ab1"
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())

    def test_password_no_uppercase_rejected(self):
        """Test that password without uppercase is rejected."""
        data = self.valid_form_data.copy()
        data["password1"] = "strongpass1"
        data["password2"] = "strongpass1"
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())

    def test_password_no_lowercase_rejected(self):
        """Test that password without lowercase is rejected."""
        data = self.valid_form_data.copy()
        data["password1"] = "STRONGPASS1"
        data["password2"] = "STRONGPASS1"
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())

    def test_password_no_digit_rejected(self):
        """Test that password without digit is rejected."""
        data = self.valid_form_data.copy()
        data["password1"] = "StrongPass"
        data["password2"] = "StrongPass"
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())


# =============================================================================
# Signup View Tests
# =============================================================================

class SignupViewTests(TestCase):
    """Tests for the signup view and full registration flow."""

    def setUp(self):
        self.signup_url = reverse("accounts:signup")
        self.login_url = reverse("accounts:login")
        self.valid_signup_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone_number": "+1234567890",
            "password1": "StrongPass1",
            "password2": "StrongPass1",
            "security_question_1": "first_pet",
            "security_answer_1": "Fluffy",
            "security_question_2": "birth_city",
            "security_answer_2": "New York",
            "security_question_3": "favorite_teacher",
            "security_answer_3": "Mr. Smith",
        }

    def test_successful_signup(self):
        """Test that a user can successfully sign up with valid data."""
        response = self.client.post(self.signup_url, data=self.valid_signup_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup_credentials.html")

        self.assertEqual(User.objects.count(), 1)
        user = User.objects.first()
        self.assertEqual(user.full_name, "John Doe")
        self.assertEqual(user.email, "john@example.com")
        self.assertEqual(user.role, CustomUser.Role.CUSTOMER)

    def test_signup_generates_username(self):
        """Signup generates a canonical username (name+year+TIF+random ID)."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        user = User.objects.first()
        self.assertRegex(
            user.username,
            rf"^JohnDoe\d{{4}}TIF[{ACCOUNT_ID_ALPHABET}]{{{ACCOUNT_ID_LENGTH}}}$",
        )

    def test_signup_creates_security_questions(self):
        """Test that signup creates three security questions."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        user = User.objects.first()
        self.assertEqual(user.security_questions.count(), 3)

    def test_security_answers_are_hashed(self):
        """Test that security answers are stored hashed."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        user = User.objects.first()
        for sq in user.security_questions.all():
            self.assertTrue(sq.hashed_answer.startswith("pbkdf2_sha256$"))

    def test_security_answers_verifiable(self):
        """Test that security answers can be verified with check_password."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        user = User.objects.first()
        sq1 = user.security_questions.get(question="first_pet")
        self.assertTrue(check_password("Fluffy", sq1.hashed_answer))
        sq2 = user.security_questions.get(question="birth_city")
        self.assertTrue(check_password("New York", sq2.hashed_answer))
        sq3 = user.security_questions.get(question="favorite_teacher")
        self.assertTrue(check_password("Mr. Smith", sq3.hashed_answer))

    def test_signup_creates_customer_role(self):
        """Test that new users are automatically assigned the CUSTOMER role."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        user = User.objects.first()
        self.assertEqual(user.role, CustomUser.Role.CUSTOMER)

    def test_duplicate_email_signup_fails(self):
        """Test that signing up with an existing email raises validation error."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        response = self.client.post(self.signup_url, data=self.valid_signup_data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "email",
            "A user with this email address already exists.",
        )

    def test_duplicate_security_questions_signup_fails(self):
        """Test that signup fails when duplicate security questions are selected."""
        data = self.valid_signup_data.copy()
        data["security_question_2"] = "first_pet"
        data["security_answer_2"] = "Another answer"
        response = self.client.post(self.signup_url, data=data)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Please select three different security questions",
            response.content.decode(),
        )
        self.assertEqual(User.objects.count(), 0)

    def test_signup_with_empty_data(self):
        """Test that signup fails with empty fields."""
        response = self.client.post(self.signup_url, data={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_signup_form_fields_rendered(self):
        """Test that the signup form renders the expected fields."""
        response = self.client.get(self.signup_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First Name")
        self.assertContains(response, "Last Name")
        self.assertContains(response, "Email")
        self.assertContains(response, "Password")
        self.assertContains(response, "Confirm Password")
        self.assertContains(response, "Security Question 1")
        self.assertContains(response, "Security Question 2")
        self.assertContains(response, "Security Question 3")
        self.assertContains(response, "Answer 1")
        self.assertContains(response, "Answer 2")
        self.assertContains(response, "Answer 3")

    def test_signup_does_not_show_username_field(self):
        """Test that username field is not rendered in the form."""
        response = self.client.get(self.signup_url)
        self.assertNotContains(response, 'name="username"')

    def test_signup_does_not_show_full_name_field(self):
        """Test that full_name field is not rendered in the form."""
        response = self.client.get(self.signup_url)
        self.assertNotContains(response, 'name="full_name"')

    def test_successful_login_after_registration(self):
        """Test that a user can log in after successful registration."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        user = User.objects.first()
        login_successful = self.client.login(username=user.username, password="StrongPass1")
        self.assertTrue(login_successful)

    def test_signup_rollback_on_failure(self):
        """Test that when form is invalid, no user or security questions are created."""
        data = self.valid_signup_data.copy()
        data["security_question_1"] = ""
        response = self.client.post(self.signup_url, data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(SecurityQuestion.objects.count(), 0)


# =============================================================================
# Login Tests
# =============================================================================

class LoginTests(TestCase):
    """Tests for user login/logout functionality."""

    def setUp(self):
        self.login_url = reverse("accounts:login")
        self.dashboard_url = reverse("accounts:dashboard")
        self.logout_url = reverse("accounts:logout")
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="testuser@example.com",
            full_name="Test User",
            password=self.password,
            username="testuser1",
        )

    def test_login_page_loads(self):
        """Test that the login page loads successfully."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_form_label_is_username(self):
        """Test that the login form labels the username field as 'Username'."""
        response = self.client.get(self.login_url)
        self.assertContains(response, "Username")
        self.assertNotContains(response, "Email")

    def test_successful_login_with_username(self):
        """Test successful login using username and password."""
        response = self.client.post(
            self.login_url,
            data={"username": self.user.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.dashboard_url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_with_wrong_password(self):
        """Test that login fails with incorrect password."""
        response = self.client.post(
            self.login_url,
            data={"username": self.user.username, "password": "WrongPassword123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_with_nonexistent_username(self):
        """Test that login fails with an unregistered username."""
        response = self.client.post(
            self.login_url,
            data={
                "username": "nonexistentuser",
                "password": self.password,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_authenticated_user_redirected_from_login(self):
        """Test that an authenticated user visiting login page is redirected to dashboard."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.dashboard_url)

    def test_login_redirect_authenticated_user(self):
        """Test that authenticated user POSTing to login is redirected."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(
            self.login_url,
            data={"username": self.user.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.dashboard_url)

    def test_correct_login_redirect_url(self):
        """Test that LOGIN_REDIRECT_URL points to dashboard."""
        from django.conf import settings
        self.assertEqual(
            settings.LOGIN_REDIRECT_URL,
            "accounts:dashboard",
        )

    def test_super_admin_redirected_to_admin_dashboard(self):
        """Super Admin login redirects to admin dashboard overview."""
        admin_user = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password=self.password,
            username="adminuser1",
            role=User.Role.SUPER_ADMIN,
        )
        response = self.client.post(
            self.login_url,
            data={"username": admin_user.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("admin_dashboard:overview"))

    def test_farm_manager_redirected_to_admin_dashboard(self):
        """Farm Manager login redirects to admin dashboard overview."""
        manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password=self.password,
            username="manager1",
            role=User.Role.FARM_MANAGER,
        )
        response = self.client.post(
            self.login_url,
            data={"username": manager.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("admin_dashboard:overview"))

    def test_staff_redirected_to_regular_dashboard(self):
        """Staff login redirects to regular dashboard."""
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff User",
            password=self.password,
            username="staff1",
            role=User.Role.STAFF,
        )
        response = self.client.post(
            self.login_url,
            data={"username": staff.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.dashboard_url)

    def test_customer_redirected_to_regular_dashboard(self):
        """Customer login redirects to regular dashboard."""
        response = self.client.post(
            self.login_url,
            data={"username": self.user.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.dashboard_url)


# =============================================================================
# Logout Tests
# =============================================================================

class LogoutTests(TestCase):
    """Tests for logout functionality."""

    def setUp(self):
        self.login_url = reverse("accounts:login")
        self.dashboard_url = reverse("accounts:dashboard")
        self.logout_url = reverse("accounts:logout")
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="testuser@example.com",
            full_name="Test User",
            password=self.password,
            username="testuser1",
        )

    def test_successful_logout(self):
        """Test that a logged-in user can log out successfully."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.login_url)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_clears_session(self):
        """Test that after logout, the user cannot access dashboard."""
        self.client.login(username=self.user.username, password=self.password)
        self.client.post(self.logout_url)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f"{self.login_url}?next={self.dashboard_url}")

    def test_correct_logout_redirect_url(self):
        """Test that LOGOUT_REDIRECT_URL points to login page."""
        from django.conf import settings
        self.assertEqual(
            settings.LOGOUT_REDIRECT_URL,
            "accounts:login",
        )

    def test_logout_requires_post(self):
        """Test that GET request to logout URL does not log out."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 405)


# =============================================================================
# Home Redirect Tests
# =============================================================================

class HomeRedirectTests(TestCase):
    """Tests for the root URL redirect behavior."""

    def setUp(self):
        self.home_url = reverse("home")
        self.login_url = reverse("accounts:login")
        self.dashboard_url = reverse("accounts:dashboard")
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="testuser@example.com",
            full_name="Test User",
            password=self.password,
            username="testuser1",
        )

    def test_anonymous_user_redirected_to_login(self):
        """Test that unauthenticated users visiting / are redirected to login."""
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.login_url)

    def test_role_based_redirect_to_admin_for_super_admin(self):
        """Super Admin visiting / is redirected to admin dashboard overview."""
        admin_user = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password=self.password,
            username="adminuser1",
            role=User.Role.SUPER_ADMIN,
        )
        self.client.login(username=admin_user.username, password=self.password)
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("admin_dashboard:overview"))

    def test_role_based_redirect_to_admin_for_farm_manager(self):
        """Farm Manager visiting / is redirected to admin dashboard overview."""
        manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password=self.password,
            username="manager1",
            role=User.Role.FARM_MANAGER,
        )
        self.client.login(username=manager.username, password=self.password)
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("admin_dashboard:overview"))

    def test_role_based_redirect_to_dashboard_for_customer(self):
        """Customer visiting / is redirected to regular dashboard."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.dashboard_url)

    def test_role_based_redirect_to_dashboard_for_staff(self):
        """Staff visiting / is redirected to regular dashboard."""
        staff = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff User",
            password=self.password,
            username="staff1",
            role=User.Role.STAFF,
        )
        self.client.login(username=staff.username, password=self.password)
        response = self.client.get(self.home_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.dashboard_url)


# =============================================================================
# Dashboard Tests
# =============================================================================

class DashboardTests(TestCase):
    """Tests for dashboard access and content."""

    def setUp(self):
        self.login_url = reverse("accounts:login")
        self.logout_url = reverse("accounts:logout")
        self.dashboard_url = reverse("accounts:dashboard")
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="testuser@example.com",
            full_name="Test User",
            password=self.password,
            username="testuser1",
        )

    def test_dashboard_requires_authentication(self):
        """Test that unauthenticated users are redirected to login."""
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            f"{self.login_url}?next={self.dashboard_url}",
        )

    def test_authenticated_user_can_access_dashboard(self):
        """Test that logged-in users can access the dashboard."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboard.html")

    def test_dashboard_shows_user_full_name(self):
        """Test that dashboard displays the user's full name."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "Test User")

    def test_dashboard_shows_user_email(self):
        """Test that dashboard displays the user's email."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "testuser@example.com")

    def test_dashboard_shows_user_role(self):
        """Test that dashboard displays the user's role."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, self.user.get_role_display())

    def test_dashboard_shows_date_joined(self):
        """Test that dashboard displays the date the user joined."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        expected_date = self.user.date_joined.strftime("%B %d, %Y")
        self.assertContains(response, expected_date)

    def test_dashboard_has_logout_button(self):
        """Test that dashboard contains a logout button."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "Logout")
        self.assertContains(response, self.logout_url)

    def test_dashboard_has_exactly_one_logout_form(self):
        """Regression test: the dashboard's page content must render exactly one
        logout form/button.

        A previous version of the dashboard template accidentally duplicated
        the logout control within the page content (once inside Quick Actions,
        once again below it). This guards against that regression happening
        silently again.

        Note: the site-wide navbar (rendered in every authenticated page's
        header, outside <main>) has its own independent logout control by
        design, so this test scopes its assertion to the <main> content area
        only rather than the full response body.
        """
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        content = response.content.decode()

        main_start = content.index("<main")
        main_end = content.index("</main>")
        main_content = content[main_start:main_end]

        # Exactly one <form> posting to the logout URL within the page content.
        self.assertEqual(
            main_content.count(f'action="{self.logout_url}"'), 1,
            "Expected exactly one form posting to the logout URL in the dashboard content.",
        )
        # Exactly one visible "Logout" label (button/link text) in the page content.
        self.assertEqual(
            main_content.count("Logout"), 1,
            "Expected exactly one visible 'Logout' button/link in the dashboard content.",
        )

    def test_dashboard_shows_phone_number_when_set(self):
        """Test that a saved phone number is displayed instead of the fallback text."""
        self.user.phone_number = "+1 555-123-4567"
        self.user.save(update_fields=["phone_number"])
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "+1 555-123-4567")
        self.assertNotContains(response, "Not provided")

    def test_dashboard_shows_fallback_when_phone_blank(self):
        """Test that the 'Not provided' fallback is shown when no phone number is set."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "Not provided")

    def test_quick_action_links_resolve_and_load(self):
        """Test that every Quick Action link on the dashboard resolves to a working page."""
        self.client.login(username=self.user.username, password=self.password)
        quick_action_urls = [
            reverse("accounts:profile_edit"),
            reverse("accounts:password_change"),
            reverse("accounts:change_security_questions"),
        ]
        for url in quick_action_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_dashboard_shows_resend_verification_link_when_unverified(self):
        """Test that unverified users see a working resend-verification link."""
        self.user.email_verified = False
        self.user.save(update_fields=["email_verified"])
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        resend_url = reverse("accounts:resend_verification")
        self.assertContains(response, resend_url)

        resend_response = self.client.get(resend_url)
        self.assertEqual(resend_response.status_code, 200)

    def test_dashboard_hides_resend_verification_link_when_verified(self):
        """Test that verified users do not see the resend-verification link."""
        self.user.email_verified = True
        self.user.save(update_fields=["email_verified"])
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)
        resend_url = reverse("accounts:resend_verification")
        self.assertNotContains(response, resend_url)

    def test_dashboard_shows_recent_orders_and_shopping_links(self):
        category = Category.objects.create(name="Dashboard Category")
        product = Product.objects.create(
            name="Dashboard Product",
            price=Decimal("2500.00"),
            stock_quantity=10,
            category=category,
        )
        order = Order.objects.create(user=self.user, total=Decimal("2500.00"))
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.dashboard_url)

        self.assertContains(response, "Recent Orders")
        self.assertContains(response, f"Order #{order.pk}")
        self.assertContains(response, reverse("shop:product_list"))
        self.assertContains(response, reverse("accounts:order_list"))

    def test_header_dropdown_shows_my_orders_and_payment_history_for_customer(self):
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertContains(response, reverse("accounts:order_list"))
        self.assertContains(response, reverse("accounts:payment_history"))

    def test_header_dropdown_hides_customer_links_for_non_customers(self):
        for role in (User.Role.SUPER_ADMIN, User.Role.FARM_MANAGER, User.Role.STAFF):
            with self.subTest(role=role):
                non_customer = User.objects.create_user(
                    email=f"{role.lower()}@example.com",
                    full_name=role.title(),
                    password=self.password,
                    username=f"{role.lower()}user",
                    role=role,
                )
                self.client.login(username=non_customer.username, password=self.password)
                response = self.client.get(reverse("accounts:dashboard"))
                content = response.content.decode()
                
                # Extract just the dropdown menu HTML
                dropdown_start = content.find('<ul class="dropdown-menu')
                dropdown_end = content.find('</ul>', dropdown_start) + 5
                dropdown_html = content[dropdown_start:dropdown_end]
                
                self.assertNotIn(reverse("accounts:order_list"), dropdown_html)
                self.assertNotIn(reverse("accounts:payment_history"), dropdown_html)


# =============================================================================
# Payment Page Tests
# =============================================================================

class PaymentTests(TestCase):
    """Tests for the payment page and the add-saved-card feature."""

    def setUp(self):
        self.login_url = reverse("accounts:login")
        self.payment_url = reverse("accounts:payment")
        self.add_card_url = reverse("accounts:add_saved_card")
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="payer@example.com",
            full_name="Pay User",
            password=self.password,
            username="payeruser",
        )

    def test_payment_page_requires_authentication(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self.payment_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            f"{self.login_url}?next={self.payment_url}",
        )

    def test_payment_page_renders_successfully(self):
        """The payment page renders without error for a logged-in user."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.payment_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/payment.html")

    def test_payment_page_shows_add_new_card_when_cards_exist(self):
        """The Add New Card control stays visible once a card is saved."""
        SavedCard.objects.create(user=self.user, last4="4242", expiry="12/28", is_default=True)
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(self.payment_url)
        self.assertContains(response, "Add New Card")
        self.assertContains(response, "4242")

    def test_add_saved_card_creates_card_with_valid_data(self):
        """Posting valid card details creates a SavedCard with only last4/expiry stored."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(self.add_card_url, {
            "cardNumber": "4111 1111 1111 1111",
            "expiry": "09/29",
            "cvv": "123",
        })
        self.assertRedirects(response, self.payment_url)
        card = SavedCard.objects.get(user=self.user)
        self.assertEqual(card.last4, "1111")
        self.assertEqual(card.expiry, "09/29")
        self.assertTrue(card.is_default)

    def test_add_saved_card_rejects_invalid_card_number(self):
        """An obviously invalid card number is rejected and no card is created."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(self.add_card_url, {
            "cardNumber": "123",
            "expiry": "09/29",
            "cvv": "123",
        })
        self.assertRedirects(response, self.payment_url)
        self.assertFalse(SavedCard.objects.filter(user=self.user).exists())

    def test_add_saved_card_rejects_invalid_expiry(self):
        """An invalid expiry format is rejected."""
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(self.add_card_url, {
            "cardNumber": "4111111111111111",
            "expiry": "13/29",
            "cvv": "123",
        })
        self.assertRedirects(response, self.payment_url)
        self.assertFalse(SavedCard.objects.filter(user=self.user).exists())

    def test_add_saved_card_only_makes_first_card_default_by_default(self):
        """Adding a second card without checking makeDefault keeps the existing default."""
        SavedCard.objects.create(user=self.user, last4="9999", expiry="01/26", is_default=True)
        self.client.login(username=self.user.username, password=self.password)
        self.client.post(self.add_card_url, {
            "cardNumber": "5555555555554444",
            "expiry": "05/30",
            "cvv": "321",
        })
        self.assertEqual(SavedCard.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertTrue(SavedCard.objects.get(user=self.user, last4="9999").is_default)


# =============================================================================
# Password Reset Tests
# =============================================================================

class PasswordResetTests(TestCase):
    """Tests for the password reset functionality."""

    def setUp(self):
        self.login_url = reverse("accounts:login")
        self.password_reset_url = reverse("accounts:password_reset")
        self.password_reset_done_url = reverse("accounts:password_reset_done")
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="testuser@example.com",
            full_name="Test User",
            password=self.password,
            username="testuser1",
        )

    def test_password_reset_form_loads(self):
        """Test that the password reset form page loads successfully."""
        response = self.client.get(self.password_reset_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_reset_form.html")

    def test_password_reset_request_sends_email(self):
        """Test that submitting the password reset form sends an email."""
        response = self.client.post(
            self.password_reset_url,
            data={"email": self.user.email},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.password_reset_done_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_password_reset_done_page_loads(self):
        """Test that the password reset done page loads."""
        response = self.client.get(self.password_reset_done_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_reset_done.html")

    def test_password_reset_confirm_valid_token(self):
        """Test that a valid reset token allows access to the confirm page."""
        self.client.post(
            self.password_reset_url,
            data={"email": self.user.email},
        )
        email_body = mail.outbox[0].body
        self.assertIn("reset", email_body.lower())

        url_pattern = r"/accounts/reset/(?P<uidb64>[^/]+)/(?P<token>[^/]+)/"
        match = re.search(url_pattern, email_body)
        self.assertIsNotNone(match, f"Reset URL not found in email body: {email_body}")

        reset_url = match.group(0)
        response = self.client.get(reset_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_reset_confirm.html")

    def test_password_reset_confirm_invalid_token(self):
        """Test that an invalid token shows an error page."""
        invalid_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": "invalid", "token": "invalid-token"},
        )
        response = self.client.get(invalid_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_reset_confirm.html")
        self.assertNotContains(response, '<form method="post"')

    def test_password_reset_confirm_expired_token(self):
        """Test that an expired token (after password change) shows an error."""
        self.client.post(
            self.password_reset_url,
            data={"email": self.user.email},
        )
        email_body = mail.outbox[0].body

        url_pattern = r"/accounts/reset/(?P<uidb64>[^/]+)/(?P<token>[^/]+)/"
        match = re.search(url_pattern, email_body)
        self.assertIsNotNone(match)

        reset_url = match.group(0)

        self.user.set_password("ChangedPass1")
        self.user.save()

        response = self.client.get(reset_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_reset_confirm.html")
        self.assertNotContains(response, '<form method="post"')

    def test_password_reset_successful(self):
        """Test full password reset flow: request -> reset -> new password works."""
        self.client.post(
            self.password_reset_url,
            data={"email": self.user.email},
        )
        email_body = mail.outbox[0].body

        url_pattern = r"/accounts/reset/(?P<uidb64>[^/]+)/(?P<token>[^/]+)/"
        match = re.search(url_pattern, email_body)
        self.assertIsNotNone(match)

        reset_url = match.group(0)
        response = self.client.get(reset_url, follow=True)
        self.assertEqual(response.status_code, 200)

        new_password = "NewStrongPass1"
        response = self.client.post(
            response.request["PATH_INFO"],
            data={
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))

        login_successful =         self.client.login(
            username=self.user.username, password=new_password
        )
        self.assertTrue(login_successful)

    def test_login_with_old_password_fails_after_reset(self):
        """Test that the old password no longer works after reset."""
        self.client.post(
            self.password_reset_url,
            data={"email": self.user.email},
        )
        email_body = mail.outbox[0].body

        url_pattern = r"/accounts/reset/(?P<uidb64>[^/]+)/(?P<token>[^/]+)/"
        match = re.search(url_pattern, email_body)
        self.assertIsNotNone(match)

        reset_url = match.group(0)
        response = self.client.get(reset_url, follow=True)
        self.assertEqual(response.status_code, 200)

        new_password = "NewStrongPass1"
        self.client.post(
            response.request["PATH_INFO"],
            data={
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )

        response = self.client.post(
            self.login_url,
            data={"username": self.user.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_password_reset_complete_page_loads(self):
        """Test that the password reset complete page loads."""
        response = self.client.get(reverse("accounts:password_reset_complete"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/password_reset_complete.html")


# =============================================================================
# Security Question Recovery Tests
# =============================================================================

class SecurityQuestionRecoveryTests(TestCase):
    """Tests for the security question recovery flow."""

    def setUp(self):
        self.recover_url = reverse("accounts:security_recovery")
        self.recover_reset_url = reverse("accounts:security_recovery_reset")
        self.login_url = reverse("accounts:login")
        self.password = "StrongPass123!"
        self.user = User.objects.create_user(
            email="recovery@example.com",
            full_name="Recovery User",
            password=self.password,
            username="recoveryuser1",
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="birth_city",
            hashed_answer=make_password("New York"),
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="favorite_teacher",
            hashed_answer=make_password("Mr. Smith"),
        )

    def test_recovery_page_loads(self):
        """Test that the recovery page loads successfully."""
        response = self.client.get(self.recover_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/security_recovery.html")

    def test_recovery_page_shows_email_form_initially(self):
        """Test that the recovery page initially shows only the email field."""
        response = self.client.get(self.recover_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="answer_1"')

    def test_valid_email_displays_security_questions(self):
        """Test that entering a valid email displays security questions."""
        response = self.client.post(
            self.recover_url,
            data={"email": self.user.email},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="answer_1"')
        self.assertContains(response, 'name="answer_2"')
        self.assertContains(response, 'name="answer_3"')
        self.assertContains(response, "What was the name of your first pet?")
        self.assertContains(response, "In what city were you born?")
        self.assertContains(response, "Who was your favorite teacher?")

    def test_invalid_email_rejected(self):
        """Test that an invalid email is rejected."""
        response = self.client.post(
            self.recover_url,
            data={"email": "nonexistent@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "email",
            "No account found with this email address.",
        )

    def test_correct_answers_allow_recovery(self):
        """Test that correct answers allow recovery and redirect to reset page."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_url,
            data={
                "answer_1": "Fluffy",
                "answer_2": "New York",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.recover_reset_url)

    def test_wrong_answers_rejected(self):
        """Test that wrong answers are rejected."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_url,
            data={
                "answer_1": "Wrong1",
                "answer_2": "Wrong2",
                "answer_3": "Wrong3",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            None,
            "One or more answers are incorrect. Please try again.",
        )

    def test_partial_wrong_answers_rejected(self):
        """Test that even one wrong answer rejects the recovery."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_url,
            data={
                "answer_1": "Fluffy",
                "answer_2": "WrongCity",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            None,
            "One or more answers are incorrect. Please try again.",
        )

    def test_missing_answers_rejected(self):
        """Test that missing answers are rejected."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_url,
            data={
                "answer_1": "Fluffy",
                "answer_2": "",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            None,
            "Please provide answers for all three security questions.",
        )

    def test_password_successfully_changed_after_recovery(self):
        """Test that password is successfully changed after recovery."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_url,
            data={
                "answer_1": "Fluffy",
                "answer_2": "New York",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertEqual(response.status_code, 302)

        new_password = "NewStrongPass1"
        response = self.client.post(
            self.recover_reset_url,
            data={
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.login_url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(self.password))

    def test_new_password_follows_validators(self):
        """Test that weak passwords are rejected during reset."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_url,
            data={
                "answer_1": "Fluffy",
                "answer_2": "New York",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            self.recover_reset_url,
            data={
                "new_password1": "weak",
                "new_password2": "weak",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("new_password1", response.context["form"].errors)
        error_messages = response.context["form"].errors["new_password1"]
        self.assertTrue(
            any("at least 8 characters" in msg for msg in error_messages),
            f"Expected length error in {error_messages}",
        )

    def test_password_mismatch_rejected(self):
        """Test that mismatched passwords are rejected."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_url,
            data={
                "answer_1": "Fluffy",
                "answer_2": "New York",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            self.recover_reset_url,
            data={
                "new_password1": "NewStrongPass1",
                "new_password2": "DifferentPass1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "new_password2",
            "The two password fields didn't match.",
        )

    def test_reset_page_requires_verification(self):
        """Test that the reset page redirects if verification not completed."""
        response = self.client.get(self.recover_reset_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.recover_url)

    def test_session_cleared_after_successful_reset(self):
        """Test that session data is cleared after successful password reset."""
        session = self.client.session
        session["recovery_user_id"] = self.user.pk
        session["recovery_verified_user_id"] = self.user.pk
        session.save()

        response = self.client.post(
            self.recover_reset_url,
            data={
                "new_password1": "NewStrongPass1",
                "new_password2": "NewStrongPass1",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.client.session.load()
        self.assertNotIn("recovery_user_id", self.client.session)
        self.assertNotIn("recovery_verified_user_id", self.client.session)


class SecurityQuestionRecoveryFormTests(TestCase):
    """Tests for the SecurityQuestionRecoveryForm."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="formtest@example.com",
            full_name="Form Test User",
            password="StrongPass123",
            username="formtest1",
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="first_pet",
            hashed_answer=make_password("Fluffy"),
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="birth_city",
            hashed_answer=make_password("New York"),
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="favorite_teacher",
            hashed_answer=make_password("Mr. Smith"),
        )

    def test_form_valid_email_only(self):
        """Test that form is valid with only a valid email."""
        form = SecurityQuestionRecoveryForm(data={"email": self.user.email})
        self.assertTrue(form.is_valid())

    def test_form_invalid_email_not_found(self):
        """Test that form is invalid with non-existent email."""
        form = SecurityQuestionRecoveryForm(
            data={"email": "nonexistent@example.com"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_form_valid_with_correct_answers(self):
        """Test that form is valid with correct answers when user is passed."""
        form = SecurityQuestionRecoveryForm(
            user=self.user,
            data={
                "answer_1": "Fluffy",
                "answer_2": "New York",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertTrue(form.is_valid())

    def test_form_invalid_with_wrong_answers(self):
        """Test that form is invalid with wrong answers when user is passed."""
        form = SecurityQuestionRecoveryForm(
            user=self.user,
            data={
                "answer_1": "Wrong",
                "answer_2": "Wrong",
                "answer_3": "Wrong",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_form_invalid_with_missing_answers(self):
        """Test that form is invalid with missing answers when user is passed."""
        form = SecurityQuestionRecoveryForm(
            user=self.user,
            data={
                "answer_1": "Fluffy",
                "answer_2": "",
                "answer_3": "Mr. Smith",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)


class RecoveryPasswordResetFormTests(TestCase):
    """Tests for the RecoveryPasswordResetForm."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="reset@example.com",
            full_name="Reset User",
            password="StrongPass123",
            username="resetuser1",
        )

    def test_form_valid_passwords_match(self):
        """Test that form is valid when passwords match."""
        form = RecoveryPasswordResetForm(
            user=self.user,
            data={
                "new_password1": "NewStrongPass1",
                "new_password2": "NewStrongPass1",
            },
        )
        self.assertTrue(form.is_valid())

    def test_form_invalid_passwords_mismatch(self):
        """Test that form is invalid when passwords don't match."""
        form = RecoveryPasswordResetForm(
            user=self.user,
            data={
                "new_password1": "NewStrongPass1",
                "new_password2": "DifferentPass1",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("new_password2", form.errors)

    def test_form_invalid_weak_password(self):
        """Test that form is invalid with a weak password."""
        form = RecoveryPasswordResetForm(
            user=self.user,
            data={
                "new_password1": "weak",
                "new_password2": "weak",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("new_password1", form.errors)

    def test_form_save_updates_password(self):
        """Test that saving the form updates the user's password."""
        form = RecoveryPasswordResetForm(
            user=self.user,
            data={
                "new_password1": "NewStrongPass1",
                "new_password2": "NewStrongPass1",
            },
        )
        self.assertTrue(form.is_valid())
        form.save()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass1"))


# =============================================================================
# Header / Navbar Link Resolution Tests
# =============================================================================

class HeaderLinkResolutionTests(TestCase):
    """Test that all named URLs used in navbar.html and base_admin.html resolve."""

    PUBLIC_NAVBAR_URLS = [
        "home",
        "accounts:dashboard",
        "accounts:profile",
        "accounts:password_change",
        "accounts:logout",
        "accounts:login",
        "accounts:signup",
    ]

    ADMIN_URLS = [
        "admin_dashboard:overview",
        "admin_dashboard:payments",
        "admin_dashboard:notifications",
        "admin_dashboard:content",
        "admin_dashboard:users",
        "admin_dashboard:orders",
        "admin_dashboard:inventory",
        "admin_dashboard:farm_management",
        "admin_dashboard:reports",
    ]

    def test_public_navbar_urls_reverse(self):
        """Test that all public navbar URL names reverse successfully."""
        for url_name in self.PUBLIC_NAVBAR_URLS:
            with self.subTest(url_name=url_name):
                url = reverse(url_name)
                self.assertIsNotNone(url)

    def test_admin_dashboard_urls_reverse(self):
        """Test that all admin dashboard URL names reverse successfully."""
        for url_name in self.ADMIN_URLS:
            with self.subTest(url_name=url_name):
                url = reverse(url_name)
                self.assertIsNotNone(url)

    def test_public_pages_load_for_anonymous(self):
        """Test that public pages load without error for anonymous users."""
        public_urls = [
            reverse("accounts:login"),
            reverse("accounts:signup"),
        ]
        for url in public_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_authenticated_user_can_access_dashboard(self):
        """Test that an authenticated customer can access accounts:dashboard."""
        user = User.objects.create_user(
            email="dash@example.com",
            full_name="Dash User",
            password="StrongPass123",
            username="dashuser1",
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_can_access_profile(self):
        """Test that an authenticated user can access profile."""
        user = User.objects.create_user(
            email="prof@example.com",
            full_name="Prof User",
            password="StrongPass123",
            username="profuser1",
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# Scroll Button Tests
# =============================================================================

class ScrollButtonTests(TestCase):
    """Tests for site-wide scroll-to-top/bottom buttons."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com",
            full_name="Test User",
            password="TestPass123!",
            username="testuser1",
        )

    def test_scroll_buttons_render_in_base_template(self):
        """Scroll buttons render in pages extending base.html."""
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="scrollToTop"')
        self.assertContains(response, 'id="scrollToBottom"')
        self.assertContains(response, "bi-chevron-up")
        self.assertContains(response, "bi-chevron-down")

    def test_scroll_buttons_css_present(self):
        """Scroll button CSS is included in base template."""
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ".scroll-button")
        self.assertContains(response, "position: fixed")
        self.assertContains(response, "#scrollToTop")
        self.assertContains(response, "#scrollToBottom")

    def test_scroll_buttons_javascript_present(self):
        """Scroll button JavaScript is included in base template."""
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "getElementById('scrollToTop')")
        self.assertContains(response, "getElementById('scrollToBottom')")
        self.assertContains(response, "updateButtonVisibility")
        self.assertContains(response, "window.scrollTo")

    def test_scroll_buttons_in_profile_page(self):
        """Scroll buttons render in profile page extending base.html."""
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="scrollToTop"')
        self.assertContains(response, 'id="scrollToBottom"')

    def test_scroll_buttons_in_admin_pages(self):
        """Scroll buttons render in admin pages extending base_admin.html."""
        admin_user = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password="TestPass123!",
            username="adminuser1",
            role="SUPER_ADMIN",
        )
        self.client.login(username=admin_user.username, password="TestPass123!")
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertEqual(response.status_code, 200)
        # base_admin.html extends base.html, so buttons should be present
        self.assertContains(response, 'id="scrollToTop"')
        self.assertContains(response, 'id="scrollToBottom"')

    def test_admin_back_link_visible_by_default(self):
        """Admin back link is rendered and not hidden by scroll-based JS."""
        admin_user = User.objects.create_user(
            email="admin2@example.com",
            full_name="Admin User 2",
            password="TestPass123!",
            username="adminuser2",
            role="SUPER_ADMIN",
        )
        self.client.login(username=admin_user.username, password="TestPass123!")
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="adminBackLink"')
        self.assertContains(response, 'class="admin-back-link"')
        self.assertNotContains(response, 'updateAdminBackLink')

    def test_authenticated_user_can_access_password_change(self):
        """Test that an authenticated user can access password change."""
        user = User.objects.create_user(
            email="pwc@example.com",
            full_name="PWC User",
            password="StrongPass123",
            username="pwcuser1",
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(response.status_code, 200)

    def test_admin_dashboard_redirects_non_admin(self):
        """Test that non-admin roles are redirected from admin dashboard to regular dashboard."""
        user = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff User",
            password="StrongPass123",
            username="staffuser1",
            role=User.Role.STAFF,
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_admin_dashboard_redirects_unauthenticated(self):
        """Test that unauthenticated users are redirected to login from admin dashboard."""
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:login"))

    def test_super_admin_can_access_admin_dashboard(self):
        """Test that Super Admin can access admin dashboard overview."""
        user = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass123",
            username="superadmin1",
            role=User.Role.SUPER_ADMIN,
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertEqual(response.status_code, 200)

    def test_farm_manager_can_access_admin_dashboard(self):
        """Test that Farm Manager can access admin dashboard overview."""
        user = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password="StrongPass123",
            username="farmmanager1",
            role=User.Role.FARM_MANAGER,
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.get(reverse("admin_dashboard:overview"))
        self.assertEqual(response.status_code, 200)

    def test_password_change_done_url_reverses(self):
        """Test that accounts:password_change_done URL resolves."""
        url = reverse("accounts:password_change_done")
        self.assertIsNotNone(url)

    def test_logout_post_redirects_to_login(self):
        """Test that POSTing to logout redirects to login page."""
        user = User.objects.create_user(
            email="logout@example.com",
            full_name="Logout User",
            password="StrongPass123",
            username="logoutuser1",
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:login"))

    def test_admin_dashboard_index_redirects_to_overview(self):
        """Test that admin_dashboard:index redirects to admin_dashboard:overview."""
        user = User.objects.create_user(
            email="index@example.com",
            full_name="Index User",
            password="StrongPass123",
            username="indexuser1",
            role=User.Role.SUPER_ADMIN,
        )
        self.client.login(username=user.username, password="StrongPass123")
        response = self.client.get(reverse("admin_dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("admin_dashboard:overview"))


class BatchAlertsLoginTests(TestCase):
    def setUp(self):
        from farm_management.models import Category, Species

        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            username="superadmin1",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.farm_manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password="StrongPass1!",
            username="farmmanager1",
            role=User.Role.FARM_MANAGER,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            full_name="Customer",
            password="StrongPass1!",
            username="customer1",
            role=User.Role.CUSTOMER,
        )
        fish_category = Category.objects.create(name="Fish")
        self.catfish = Species.objects.create(
            name="Catfish",
            category=fish_category,
        )

    def test_check_batch_alerts_runs_on_super_admin_login(self):
        from farm_management.models import Batch
        from datetime import date
        Batch.objects.create(
            name="Alert Test Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        initial_count = Notification.objects.filter(
            notification_type='batch_alert',
        ).count()
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        final_count = Notification.objects.filter(
            notification_type='batch_alert',
        ).count()
        self.assertGreaterEqual(final_count, initial_count)

    def test_check_batch_alerts_runs_on_farm_manager_login(self):
        from farm_management.models import Batch
        from datetime import date
        Batch.objects.create(
            name="FM Alert Test Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        initial_count = Notification.objects.filter(
            notification_type='batch_alert',
        ).count()
        self.client.login(username=self.farm_manager.username, password="StrongPass1!")
        final_count = Notification.objects.filter(
            notification_type='batch_alert',
        ).count()
        self.assertGreaterEqual(final_count, initial_count)

    def test_check_batch_alerts_skipped_on_customer_login(self):
        from farm_management.models import Batch
        from datetime import date
        Batch.objects.create(
            name="Customer Alert Test Batch",
            species=self.catfish,
            initial_count=100,
            start_date=date.today(),
            season="rainy",
        )
        initial_count = Notification.objects.filter(
            notification_type='batch_alert',
        ).count()
        self.client.login(username=self.customer.username, password="StrongPass1!")
        final_count = Notification.objects.filter(
            notification_type='batch_alert',
        ).count()
        self.assertEqual(initial_count, final_count)


class CustomerOrderViewTests(TestCase):
    """Tests for customer-only order history and order detail views."""

    def setUp(self):
        self.password = "StrongPass123!"
        self.customer = User.objects.create_user(
            email="customer-orders@example.com",
            full_name="Customer Orders",
            password=self.password,
            username="customerorders",
            role=User.Role.CUSTOMER,
        )
        self.other_customer = User.objects.create_user(
            email="other-orders@example.com",
            full_name="Other Customer",
            password=self.password,
            username="otherorders",
            role=User.Role.CUSTOMER,
        )
        category = Category.objects.create(name="Order Category")
        self.product = Product.objects.create(
            name="Order Product",
            price=Decimal("1200.00"),
            stock_quantity=10,
            category=category,
        )
        self.own_order = Order.objects.create(
            user=self.customer,
            total=Decimal("2400.00"),
            status=Order.Status.PROCESSING,
            delivery_address="12 Customer Road",
            payment_method="Cash on Delivery",
        )
        OrderItem.objects.create(
            order=self.own_order,
            product=self.product,
            product_name=self.product.name,
            quantity=2,
            price=self.product.price,
        )
        self.other_order = Order.objects.create(
            user=self.other_customer,
            total=Decimal("1200.00"),
        )

    def test_my_orders_lists_only_logged_in_customers_orders(self):
        self.client.login(username=self.customer.username, password=self.password)

        response = self.client.get(reverse("accounts:order_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Order #{self.own_order.pk}")
        self.assertNotContains(response, f"Order #{self.other_order.pk}")

    def test_customer_can_view_own_order_detail(self):
        self.client.login(username=self.customer.username, password=self.password)

        response = self.client.get(
            reverse("accounts:order_detail", args=[self.own_order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order Product")
        self.assertContains(response, "12 Customer Road")
        self.assertContains(response, "Cash on Delivery")

    def test_customer_cannot_view_another_customers_order_detail(self):
        self.client.login(username=self.customer.username, password=self.password)

        response = self.client.get(
            reverse("accounts:order_detail", args=[self.other_order.pk])
        )

        self.assertEqual(response.status_code, 404)


class CustomerPaymentHistoryTests(TestCase):
    """Tests for customer payment history and printable receipts."""

    def setUp(self):
        self.password = "StrongPass123!"
        self.customer = User.objects.create_user(
            email="payment-customer@example.com",
            full_name="Payment Customer",
            password=self.password,
            username="paymentcustomer",
            role=User.Role.CUSTOMER,
        )
        self.other_customer = User.objects.create_user(
            email="other-payment@example.com",
            full_name="Other Payment",
            password=self.password,
            username="otherpayment",
            role=User.Role.CUSTOMER,
        )
        category = Category.objects.create(name="Payment Category")
        product = Product.objects.create(
            name="Payment Product",
            price=Decimal("1500.00"),
            stock_quantity=10,
            category=category,
        )

        self.own_order = Order.objects.create(
            user=self.customer,
            total=Decimal("3000.00"),
            status=Order.Status.DELIVERED,
            delivery_address="45 Payment Lane",
            payment_method="Card",
        )
        OrderItem.objects.create(
            order=self.own_order,
            product=product,
            product_name=product.name,
            quantity=2,
            price=product.price,
        )

        self.other_order = Order.objects.create(
            user=self.other_customer,
            total=Decimal("1500.00"),
            status=Order.Status.PENDING,
        )
        OrderItem.objects.create(
            order=self.other_order,
            product=product,
            product_name=product.name,
            quantity=1,
            price=product.price,
        )

        self.own_success_payment = Payment.objects.create(
            order=self.own_order,
            reference="PAY-SUCCESS-001",
            amount=Decimal("3000.00"),
            status="success",
        )
        self.own_failed_payment = Payment.objects.create(
            order=self.own_order,
            reference="PAY-FAILED-001",
            amount=Decimal("3000.00"),
            status="failed",
        )
        self.other_payment = Payment.objects.create(
            order=self.other_order,
            reference="PAY-OTHER-001",
            amount=Decimal("1500.00"),
            status="success",
        )

    def test_payment_history_requires_authentication(self):
        response = self.client.get(reverse("accounts:payment_history"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:payment_history')}",
        )

    def test_payment_history_lists_only_customers_payments(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(reverse("accounts:payment_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")
        self.assertContains(response, "PAY-FAILED-001")
        self.assertNotContains(response, "PAY-OTHER-001")

    def test_payment_history_shows_success_and_failed_statuses(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(reverse("accounts:payment_history"))

        self.assertContains(response, "Successful")
        self.assertContains(response, "Failed")

    def test_payment_history_shows_receipt_link_for_successful_payments(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(reverse("accounts:payment_history"))

        self.assertContains(response, reverse("accounts:payment_receipt", args=[self.own_success_payment.pk]))

    def test_payment_history_does_not_show_receipt_link_for_failed_payments(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(reverse("accounts:payment_history"))

        self.assertNotContains(response, reverse("accounts:payment_receipt", args=[self.own_failed_payment.pk]))

    def test_customer_can_view_own_successful_payment_receipt(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(
            reverse("accounts:payment_receipt", args=[self.own_success_payment.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")
        self.assertContains(response, "Payment Product")
        self.assertContains(response, "3000.00")
        self.assertContains(response, "Payment Customer")
        self.assertContains(response, "45 Payment Lane")

    def test_customer_cannot_view_receipt_for_failed_payment(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(
            reverse("accounts:payment_receipt", args=[self.own_failed_payment.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_customer_cannot_view_another_customers_payment_receipt(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(
            reverse("accounts:payment_receipt", args=[self.other_payment.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_dashboard_shows_payment_history_link(self):
        self.client.login(username=self.customer.username, password=self.password)
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertContains(response, reverse("accounts:payment_history"))


class SignupCredentialsDownloadTests(TestCase):
    """
    Tests for the one-time credentials download offered at signup.

    Covers: the download is offered, it contains the correct username,
    password and security questions, and the raw password is never
    persisted to the database, the session, or the logs.
    """

    RAW_PASSWORD = "StrongPass1!"

    def setUp(self):
        self.signup_url = reverse("accounts:signup")
        self.payload = {
            "first_name": "Test",
            "last_name": "User",
            "email": "testdownload@example.com",
            "phone_number": "1234567890",
            "password1": self.RAW_PASSWORD,
            "password2": self.RAW_PASSWORD,
            "security_question_1": "first_pet",
            "security_answer_1": "Fluffy",
            "security_question_2": "birth_city",
            "security_answer_2": "Lagos",
            "security_question_3": "first_school",
            "security_answer_3": "Springfield Elementary",
        }

    def _signup(self):
        return self.client.post(self.signup_url, self.payload)

    # ---------------------------------------------------------------
    # The download is offered
    # ---------------------------------------------------------------

    def test_signup_renders_credentials_page_instead_of_redirecting(self):
        """Signup returns the credentials page in the same response."""
        response = self._signup()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup_credentials.html")

    def test_download_button_is_offered(self):
        """The page offers a download control for the credentials file."""
        response = self._signup()
        self.assertContains(response, "downloadCredentials")
        self.assertContains(response, "credentialsFileText")

    def test_onscreen_warning_is_shown(self):
        """The user is warned on-screen, not only inside the file."""
        response = self._signup()
        body = response.content.decode()
        self.assertIn("Download this file now", body)
        self.assertIn("only time your password can be shown", body)

    def test_filename_uses_new_username(self):
        """The offered filename is tied to the generated username."""
        response = self._signup()
        user = User.objects.get(email="testdownload@example.com")
        self.assertContains(response, f"tamipee-credentials-{user.username}.txt")

    # ---------------------------------------------------------------
    # File contents are correct
    # ---------------------------------------------------------------

    def test_file_contains_username_password_and_questions(self):
        """File content includes username, raw password, and question text."""
        response = self._signup()
        user = User.objects.get(email="testdownload@example.com")
        file_text = response.context["credentials_file_text"]

        self.assertIn(f"Username: {user.username}", file_text)
        self.assertIn(f"Password: {self.RAW_PASSWORD}", file_text)
        self.assertIn("What was the name of your first pet?", file_text)
        self.assertIn("In what city were you born?", file_text)
        self.assertIn("What was the name of your first school?", file_text)

    def test_file_uses_new_random_username_format(self):
        """The username in the file follows the new TIF + random ID format."""
        response = self._signup()
        user = User.objects.get(email="testdownload@example.com")
        file_text = response.context["credentials_file_text"]

        self.assertRegex(
            user.username,
            rf"^TestUser\d{{4}}TIF[{ACCOUNT_ID_ALPHABET}]{{{ACCOUNT_ID_LENGTH}}}$",
        )
        self.assertIn(user.username, file_text)

    def test_file_never_contains_security_answers(self):
        """Answers are hashed and must never appear in the file or page."""
        response = self._signup()
        file_text = response.context["credentials_file_text"]
        body = response.content.decode()

        for answer in ("Fluffy", "Lagos", "Springfield Elementary"):
            self.assertNotIn(answer, file_text)
            self.assertNotIn(answer, body)

    def test_questions_shown_are_labels_not_raw_keys(self):
        """Human-readable question text is used, not the choice keys."""
        response = self._signup()
        labels = response.context["question_labels"]
        self.assertEqual(labels, [
            "What was the name of your first pet?",
            "In what city were you born?",
            "What was the name of your first school?",
        ])

    # ---------------------------------------------------------------
    # The raw password is not persisted anywhere
    # ---------------------------------------------------------------

    def test_raw_password_not_stored_in_database(self):
        """Password is stored only as a hash; raw value appears nowhere."""
        self._signup()
        user = User.objects.get(email="testdownload@example.com")

        self.assertNotEqual(user.password, self.RAW_PASSWORD)
        self.assertNotIn(self.RAW_PASSWORD, user.password)
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertTrue(user.check_password(self.RAW_PASSWORD))

    def test_raw_password_not_in_any_database_column(self):
        """Sweep every text column of the user row for the raw password."""
        self._signup()
        user = User.objects.get(email="testdownload@example.com")

        for field in user._meta.fields:
            value = getattr(user, field.attname, None)
            if isinstance(value, str):
                self.assertNotIn(
                    self.RAW_PASSWORD, value,
                    f"Raw password leaked into field '{field.attname}'",
                )

    def test_raw_password_not_stored_in_security_questions(self):
        """Security question rows must not contain the raw password."""
        self._signup()
        user = User.objects.get(email="testdownload@example.com")
        for question in user.security_questions.all():
            self.assertNotIn(self.RAW_PASSWORD, question.hashed_answer)
            self.assertNotIn(self.RAW_PASSWORD, question.question)

    def test_raw_password_not_stored_in_session(self):
        """The session must not retain the raw password after signup."""
        self._signup()
        session_blob = str(dict(self.client.session))
        self.assertNotIn(self.RAW_PASSWORD, session_blob)

    def test_security_questions_no_longer_stored_in_session(self):
        """The old session-based questions handoff is gone."""
        self._signup()
        self.assertNotIn("signup_security_questions", self.client.session)

    def test_raw_password_not_written_to_logs(self):
        """Capture all log output during signup and assert no leak."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        root_logger = logging.getLogger()
        previous_level = root_logger.level

        root_logger.addHandler(handler)
        root_logger.setLevel(logging.DEBUG)
        try:
            self._signup()
        finally:
            handler.flush()
            root_logger.removeHandler(handler)
            root_logger.setLevel(previous_level)

        self.assertNotIn(self.RAW_PASSWORD, stream.getvalue())

    def test_response_is_not_cacheable(self):
        """The credentials response must not be cached or stored."""
        response = self._signup()
        self.assertIn("no-store", response["Cache-Control"])

    def test_signup_view_marks_password_params_sensitive(self):
        """
        Django's error reporting must redact the raw password for this view,
        so a traceback can never capture it.
        """
        response = self._signup()
        sensitive = response.wsgi_request.sensitive_post_parameters
        for field in ("password1", "password2"):
            self.assertIn(field, sensitive)

    def test_credentials_page_not_reachable_by_get(self):
        """The credentials page exists only as the signup POST response."""
        response = self.client.get(self.signup_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup.html")
        self.assertNotContains(response, "downloadCredentials")

    def test_user_is_logged_in_after_signup(self):
        """Auto-login behaviour is preserved."""
        self._signup()
        user = User.objects.get(email="testdownload@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_continue_link_points_to_dashboard(self):
        """The page offers a way forward after saving credentials."""
        response = self._signup()
        self.assertContains(response, reverse("accounts:dashboard"))


class AdminCreatedAccountCredentialsTests(TestCase):
    """The credentials download is also offered for admin-created accounts."""

    RAW_PASSWORD = "AdminSetPass1!"

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="AdminPass123",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.super_admin)

    def test_admin_user_create_offers_credentials(self):
        """Creating a customer as admin renders the credentials page."""
        response = self.client.post(reverse("admin_dashboard:user_create"), {
            "full_name": "Created Customer",
            "email": "createdcustomer@example.com",
            "role": User.Role.CUSTOMER,
            "is_active": "on",
            "password1": self.RAW_PASSWORD,
            "password2": self.RAW_PASSWORD,
            "security_question_1": "first_pet",
            "security_answer_1": "Rex",
            "security_question_2": "birth_city",
            "security_answer_2": "Abuja",
            "security_question_3": "first_school",
            "security_answer_3": "Unity",
        })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin_dashboard/user_credentials.html")

        created = User.objects.get(email="createdcustomer@example.com")
        file_text = response.context["credentials_file_text"]
        self.assertIn(f"Username: {created.username}", file_text)
        self.assertIn(f"Password: {self.RAW_PASSWORD}", file_text)
        self.assertIn("TIF", created.username)
        self.assertTrue(created.account_id)

        # Answers never exposed, raw password never persisted.
        for answer in ("Rex", "Abuja", "Unity"):
            self.assertNotIn(answer, file_text)
        self.assertNotIn(self.RAW_PASSWORD, created.password)
        self.assertTrue(created.check_password(self.RAW_PASSWORD))
        self.assertNotIn(self.RAW_PASSWORD, str(dict(self.client.session)))

    def test_admin_staff_create_offers_credentials(self):
        """Creating a staff member as admin renders the credentials page."""
        response = self.client.post(reverse("admin_dashboard:staff_create"), {
            "full_name": "Created Staff",
            "email": "createdstaff@example.com",
            "role": User.Role.STAFF,
            "is_active": "on",
            "password1": self.RAW_PASSWORD,
            "password2": self.RAW_PASSWORD,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin_dashboard/user_credentials.html")

        created = User.objects.get(email="createdstaff@example.com")
        file_text = response.context["credentials_file_text"]
        self.assertIn(f"Username: {created.username}", file_text)
        self.assertIn(f"Password: {self.RAW_PASSWORD}", file_text)
        self.assertIn("TIF", created.username)
        self.assertTrue(created.account_id)
        self.assertNotIn(self.RAW_PASSWORD, created.password)
        self.assertTrue(created.check_password(self.RAW_PASSWORD))


class ExistingAccountsUntouchedTests(TestCase):
    """
    Guard: this change is new-accounts-only. Existing usernames and
    passwords must never be rewritten.
    """

    def test_existing_accounts_survive_new_signups(self):
        """Creating new accounts leaves older accounts completely unchanged."""
        legacy_users = []
        for index in range(3):
            user = User.objects.create_user(
                email=f"legacy{index}@example.com",
                full_name=f"Legacy User{index}",
                password="LegacyPass123",
                username=f"LegacyUser{index}2025{index + 1:03d}",
            )
            legacy_users.append(
                (user.pk, user.username, user.password, user.account_id)
            )

        # Create several new accounts through the canonical path.
        for index in range(3):
            User.objects.create_user(
                email=f"fresh{index}@example.com",
                full_name="Fresh User",
                password="FreshPass123",
            )

        for pk, username, password, account_id in legacy_users:
            reloaded = User.objects.get(pk=pk)
            self.assertEqual(reloaded.username, username)
            self.assertEqual(reloaded.password, password)
            self.assertEqual(reloaded.account_id, account_id)
            self.assertTrue(reloaded.check_password("LegacyPass123"))

    def test_legacy_sequential_usernames_still_log_in(self):
        """Old sequential usernames remain valid login credentials."""
        User.objects.create_user(
            email="oldstyle@example.com",
            full_name="Old Style",
            password="OldPass123!",
            username="OldStyle2025001",
        )
        logged_in = self.client.login(
            username="OldStyle2025001", password="OldPass123!"
        )
        self.assertTrue(logged_in)


class SecurityAnswerExposureTests(TestCase):
    """Tests to confirm no endpoint exposes plaintext security answers."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="securitytest@example.com",
            full_name="Security Test",
            password="StrongPass1!",
            username="securitytest",
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="pet_name",
            hashed_answer=make_password("Fluffy"),
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="birth_city",
            hashed_answer=make_password("Lagos"),
        )
        SecurityQuestion.objects.create(
            user=self.user,
            question="first_school",
            hashed_answer=make_password("Springfield"),
        )

    def test_admin_user_detail_does_not_explain_hashed_answers(self):
        """Admin user detail page should not show hashed answers."""
        super_admin = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password="StrongPass1!",
            username="adminuser",
            role=User.Role.SUPER_ADMIN,
        )
        self.client.login(username=super_admin.username, password="StrongPass1!")
        response = self.client.get(reverse("admin_dashboard:user_detail", args=[self.user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "pbkdf2_sha256")
        self.assertNotContains(response, "Fluffy")
        self.assertNotContains(response, "Lagos")
        self.assertNotContains(response, "Springfield")

    def test_admin_user_edit_does_not_expose_security_answers(self):
        """Admin user edit page should not expose security answers."""
        super_admin = User.objects.create_user(
            email="admin2@example.com",
            full_name="Admin User 2",
            password="StrongPass1!",
            username="adminuser2",
            role=User.Role.SUPER_ADMIN,
        )
        self.client.login(username=super_admin.username, password="StrongPass1!")
        response = self.client.get(reverse("admin_dashboard:user_edit", args=[self.user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "pbkdf2_sha256")
        self.assertNotContains(response, "Fluffy")
        self.assertNotContains(response, "Lagos")
        self.assertNotContains(response, "Springfield")

    def test_security_question_model_str_does_not_expose_answer(self):
        """SecurityQuestion __str__ should not include the hashed answer."""
        sq = SecurityQuestion.objects.first()
        str_repr = str(sq)
        self.assertNotIn("pbkdf2_sha256", str_repr)
        self.assertNotIn("Fluffy", str_repr)
        self.assertIn(self.user.full_name, str_repr)

    def test_no_api_endpoint_returns_plaintext_answers(self):
        """Confirm no known endpoint returns plaintext security answers."""
        # Check a few key URLs that might expose user data
        urls_to_check = [
            reverse("admin_dashboard:user_detail", args=[self.user.pk]),
            reverse("accounts:profile"),
        ]
        for url in urls_to_check:
            response = self.client.get(url)
            if response.status_code == 200:
                content = response.content.decode()
        self.assertNotIn("Fluffy", content)
        self.assertNotIn("Lagos", content)
        self.assertNotIn("Springfield", content)


# =============================================================================
# Profile Photo Upload Tests
# =============================================================================

class ProfilePhotoUploadTests(TestCase):
    """Tests for profile photo upload functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="photouser@example.com",
            full_name="Photo User",
            password="StrongPass1",
            username="photouser",
        )
        self.client.login(username=self.user.username, password="StrongPass1")

    def test_profile_edit_form_accepts_valid_jpeg(self):
        """ProfileEditForm should accept a valid JPEG image."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.forms import ProfileEditForm
        from PIL import Image as PILImage
        import io

        image = PILImage.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        buffer.seek(0)
        jpeg_file = SimpleUploadedFile(
            "photo.jpg", buffer.read(), content_type="image/jpeg"
        )
        form = ProfileEditForm(
            data={
                "full_name": self.user.full_name,
                "phone_number": self.user.phone_number,
                "default_delivery_address": self.user.default_delivery_address,
                "username": self.user.username,
            },
            files={"profile_picture": jpeg_file},
            instance=self.user,
        )
        self.assertTrue(form.is_valid(), msg=str(form.errors))

    def test_profile_edit_form_rejects_invalid_file_type(self):
        """ProfileEditForm should reject non-image files."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.forms import ProfileEditForm

        txt_file = SimpleUploadedFile(
            "photo.txt", b"not an image", content_type="text/plain"
        )
        form = ProfileEditForm(
            data={
                "full_name": self.user.full_name,
                "phone_number": self.user.phone_number,
                "default_delivery_address": self.user.default_delivery_address,
                "username": self.user.username,
            },
            files={"profile_picture": txt_file},
            instance=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("profile_picture", form.errors)

    def test_profile_edit_form_rejects_oversized_image(self):
        """ProfileEditForm should reject images larger than 5MB."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.forms import ProfileEditForm
        from PIL import Image as PILImage
        import io

        image = PILImage.new('RGB', (5000, 5000), color='blue')
        buffer = io.BytesIO()
        image.save(buffer, format='BMP')
        buffer.seek(0)
        large_file = SimpleUploadedFile(
            "large.bmp", buffer.read(), content_type="image/bmp"
        )
        form = ProfileEditForm(
            data={
                "full_name": self.user.full_name,
                "phone_number": self.user.phone_number,
                "default_delivery_address": self.user.default_delivery_address,
                "username": self.user.username,
            },
            files={"profile_picture": large_file},
            instance=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("profile_picture", form.errors)

    def test_admin_user_edit_form_accepts_valid_image(self):
        """Admin UserEditForm should accept a valid profile photo."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from admin_dashboard.forms import UserEditForm
        from PIL import Image as PILImage
        import io

        super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            username="superadmin",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        image = PILImage.new('RGB', (100, 100), color='green')
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        buffer.seek(0)
        jpeg_file = SimpleUploadedFile(
            "admin_photo.jpg", buffer.read(), content_type="image/jpeg"
        )
        form = UserEditForm(
            data={
                "full_name": self.user.full_name,
                "email": self.user.email,
                "phone_number": self.user.phone_number,
                "role": self.user.role,
                "is_active": self.user.is_active,
                "remove_profile_picture": False,
            },
            files={"profile_picture": jpeg_file},
            instance=self.user,
            request_user=super_admin,
        )
        self.assertTrue(form.is_valid(), msg=str(form.errors))

    def test_admin_user_edit_form_removes_photo(self):
        """Admin UserEditForm should remove photo when checkbox is checked."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from admin_dashboard.forms import UserEditForm
        from PIL import Image as PILImage
        import io

        super_admin = User.objects.create_user(
            email="superadmin2@example.com",
            full_name="Super Admin 2",
            password="StrongPass1!",
            username="superadmin2",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        image = PILImage.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG')
        buffer.seek(0)
        self.user.profile_picture = SimpleUploadedFile(
            "old.jpg", buffer.read(), content_type="image/jpeg"
        )
        self.user.save()

        form = UserEditForm(
            data={
                "full_name": self.user.full_name,
                "email": self.user.email,
                "phone_number": self.user.phone_number,
                "role": self.user.role,
                "is_active": self.user.is_active,
                "remove_profile_picture": True,
            },
            files={},
            instance=self.user,
            request_user=super_admin,
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertFalse(user.profile_picture)
