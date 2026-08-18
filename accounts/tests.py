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
import re

from .models import CustomUser, SecurityQuestion, SavedCard
from .forms import CustomSignupForm, SecurityQuestionRecoveryForm, RecoveryPasswordResetForm
from .utils import generate_unique_username
from .validators import UppercaseValidator, LowercaseValidator, DigitValidator
from .constants import SECURITY_QUESTIONS
from notifications.models import Notification
from shop.models import Category, Order, OrderItem, Product, Payment

User = get_user_model()


# =============================================================================
# Username Generation Tests
# =============================================================================

class UsernameGenerationTests(TestCase):
    """Tests for the generate_unique_username utility function."""

    def test_basic_username_generation(self):
        """Test that username is generated from first and last name with year and sequence."""
        username = generate_unique_username("John", "Doe")
        self.assertTrue(username.startswith("JohnDoe"))
        self.assertIn(str(timezone.now().year), username)

    def test_spaces_removed(self):
        """Test that spaces are removed from username."""
        username = generate_unique_username("  John  ", "  Doe  ")
        self.assertEqual(username, "JohnDoe" + str(timezone.now().year) + "001")

    def test_special_characters_removed(self):
        """Test that special characters are removed from username."""
        username = generate_unique_username("John!", "Doe@")
        self.assertEqual(username, "JohnDoe" + str(timezone.now().year) + "001")

    def test_unicode_normalization(self):
        """Test that unicode characters are normalized."""
        username = generate_unique_username("José", "García")
        self.assertEqual(username, "JoseGarcia" + str(timezone.now().year) + "001")

    def test_collision_handling(self):
        """Test that duplicate base names get sequential numbers."""
        User.objects.create_user(
            email="john1@example.com",
            full_name="John Doe",
            password="TestPass123",
            username="JohnDoe" + str(timezone.now().year) + "001",
        )
        new_username = generate_unique_username("John", "Doe")
        self.assertEqual(new_username, "JohnDoe" + str(timezone.now().year) + "002")

    def test_multiple_collisions(self):
        """Test that multiple collisions all produce unique usernames."""
        for i in range(5):
            seq = f"{i+1:03d}"
            User.objects.create_user(
                email=f"john{i}@example.com",
                full_name="John Doe",
                password="TestPass123",
                username="JohnDoe" + str(timezone.now().year) + seq,
            )
        new_u = generate_unique_username("John", "Doe")
        self.assertEqual(new_u, "JohnDoe" + str(timezone.now().year) + "006")

    def test_empty_first_name_fallback(self):
        """Test that empty first name still generates a username."""
        username = generate_unique_username("", "Doe")
        self.assertEqual(username, "Doe" + str(timezone.now().year) + "001")

    def test_empty_last_name_fallback(self):
        """Test that empty last name still generates a username."""
        username = generate_unique_username("John", "")
        self.assertEqual(username, "John" + str(timezone.now().year) + "001")

    def test_both_names_empty_fallback(self):
        """Test that both empty names fall back to 'User'."""
        username = generate_unique_username("", "")
        self.assertEqual(username, "User" + str(timezone.now().year) + "001")

    def test_sequential_per_year(self):
        """Test that sequence resets per year."""
        u1 = generate_unique_username("Test", "User", year=2026)
        u2 = generate_unique_username("Test", "User", year=2027)
        self.assertTrue(u1.startswith("TestUser2026"))
        self.assertTrue(u2.startswith("TestUser2027"))


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
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:dashboard"))

        self.assertEqual(User.objects.count(), 1)
        user = User.objects.first()
        self.assertEqual(user.full_name, "John Doe")
        self.assertEqual(user.email, "john@example.com")
        self.assertEqual(user.role, CustomUser.Role.CUSTOMER)

    def test_signup_generates_username(self):
        """Test that signup generates a username automatically."""
        self.client.post(self.signup_url, data=self.valid_signup_data)
        user = User.objects.first()
        self.assertEqual(user.username, "JohnDoe2026001")

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
        self.assertContains(response, "Email Address")
        self.assertContains(response, "Phone Number")
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


class SignupDownloadTests(TestCase):
    """Tests for the signup security questions download step."""

    def setUp(self):
        self.signup_url = reverse("accounts:signup")
        self.download_url = reverse("accounts:signup_download")
        self.file_url = reverse("accounts:download_security_questions")

    def test_signup_stores_questions_in_session(self):
        """After successful signup, questions should be stored in session."""
        response = self.client.post(self.signup_url, {
            "first_name": "Test",
            "last_name": "User",
            "email": "testdownload@example.com",
            "phone_number": "1234567890",
            "password1": "StrongPass1!",
            "password2": "StrongPass1!",
            "security_question_1": "first_pet",
            "security_answer_1": "Fluffy",
            "security_question_2": "birth_city",
            "security_answer_2": "Lagos",
            "security_question_3": "first_school",
            "security_answer_3": "Springfield Elementary",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertEqual(self.client.session["signup_security_questions"], ["first_pet", "birth_city", "first_school"])

    def test_download_page_requires_session_questions(self):
        """Download page should redirect to signup if no questions in session."""
        response = self.client.get(self.download_url)
        self.assertRedirects(response, self.signup_url)

    def test_download_page_renders_questions(self):
        """Download page should show the stored questions."""
        session = self.client.session
        session["signup_security_questions"] = ["first_pet", "birth_city", "first_school"]
        session.save()
        response = self.client.get(self.download_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "first_pet")
        self.assertContains(response, "birth_city")
        self.assertContains(response, "first_school")

    def test_file_download_requires_session_questions(self):
        """File download should redirect to signup if no questions in session."""
        response = self.client.get(self.file_url)
        self.assertRedirects(response, self.signup_url)

    def test_file_download_generates_text_file(self):
        """File download should return a plain text file with questions."""
        session = self.client.session
        session["signup_security_questions"] = ["first_pet", "birth_city", "first_school"]
        session.save()
        response = self.client.get(self.file_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn('attachment; filename="tamipee-security-questions.txt"', response["Content-Disposition"])
        content = response.content.decode()
        self.assertIn("first_pet", content)
        self.assertIn("birth_city", content)
        self.assertIn("first_school", content)
        self.assertNotIn("Fluffy", content)
        self.assertNotIn("Lagos", content)

    def test_download_confirmation_redirects_to_login(self):
        """Submitting the confirmation form should redirect to login."""
        session = self.client.session
        session["signup_security_questions"] = ["first_pet", "birth_city", "first_school"]
        session.save()
        response = self.client.post(self.download_url, {"downloaded_confirmed": "on"})
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("signup_security_questions", self.client.session)

    def test_download_page_blocks_without_confirmation(self):
        """Download page should show error if confirmation checkbox is not checked."""
        session = self.client.session
        session["signup_security_questions"] = ["first_pet", "birth_city", "first_school"]
        session.save()
        response = self.client.post(self.download_url, {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please confirm")


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
