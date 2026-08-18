from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import CustomUser, SecurityQuestion
from .constants import SECURITY_QUESTIONS
from .utils import generate_unique_username

User = get_user_model()


class CustomAuthenticationForm(AuthenticationForm):
    """
    Custom Authentication Form for farm_proc_tamipee.

    Uses username-based authentication instead of email.
    """

    username = forms.CharField(
        label=_("Username"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )

    class Meta:
        model = CustomUser
        fields = ("username", "password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = ""
        self.fields["username"].widget.attrs.pop("placeholder", None)
        self.fields["username"].widget.attrs["placeholder"] = "Enter your username"
        self.fields["password"].widget.attrs["placeholder"] = "Enter your password"

    def confirm_login_allowed(self, user):
        """
        Control whether a user can log in.
        Prevents inactive users from logging in.
        """
        if not user.is_active:
            raise forms.ValidationError(
                _("This account is inactive."),
                code="inactive",
            )


class CustomSignupForm(UserCreationForm):
    """
    Custom Signup Form for farm_proc_tamipee.

    Collects first name, last name, password,
    and three security question/answer pairs. The username and full_name
    fields are auto-generated and not exposed to the user.
    """

    first_name = forms.CharField(
        label=_("First Name"),
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your first name",
                "autofocus": True,
            }
        ),
    )
    last_name = forms.CharField(
        label=_("Last Name"),
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your last name",
            }
        ),
    )

    # Security question fields
    security_question_1 = forms.TypedChoiceField(
        label=_("Security Question 1"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    security_answer_1 = forms.CharField(
        label=_("Answer 1"),
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your answer",
            }
        ),
    )
    security_question_2 = forms.TypedChoiceField(
        label=_("Security Question 2"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    security_answer_2 = forms.CharField(
        label=_("Answer 2"),
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your answer",
            }
        ),
    )
    security_question_3 = forms.TypedChoiceField(
        label=_("Security Question 3"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    security_answer_3 = forms.CharField(
        label=_("Answer 3"),
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your answer",
            }
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Customize password fields
        self.fields["password1"].label = _("Password")
        self.fields["password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Create a strong password",
        })
        self.fields["password1"].help_text = _(
            "Your password must contain at least 8 characters, "
            "including uppercase, lowercase, and a digit."
        )

        self.fields["password2"].label = _("Confirm Password")
        self.fields["password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Re-enter your password",
        })
        self.fields["password2"].help_text = _("Enter the same password as above, for verification.")

    def clean_security_questions(self):
        """
        Validate that all three security questions are selected,
        no duplicates exist, and all answers are provided.
        """
        q1 = self.cleaned_data.get("security_question_1")
        q2 = self.cleaned_data.get("security_question_2")
        q3 = self.cleaned_data.get("security_question_3")
        a1 = self.cleaned_data.get("security_answer_1")
        a2 = self.cleaned_data.get("security_answer_2")
        a3 = self.cleaned_data.get("security_answer_3")

        # Check all questions are selected
        if not q1 or not q2 or not q3:
            raise forms.ValidationError(
                _("Please select all three security questions."),
                code="missing_security_questions",
            )

        # Check no duplicate questions
        if len({q1, q2, q3}) != 3:
            raise forms.ValidationError(
                _("Please select three different security questions. Duplicate questions are not allowed."),
                code="duplicate_security_questions",
            )

        # Check all answers are provided
        if not a1 or not a2 or not a3:
            raise forms.ValidationError(
                _("Please provide answers for all three security questions."),
                code="missing_security_answers",
            )

        return [q1, q2, q3], [a1, a2, a3]

    def clean_email(self):
        """
        Validate that the email is unique, if provided.
        """
        email = self.cleaned_data.get("email")
        if email:
            if CustomUser.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError(
                    _("A user with this email address already exists."),
                    code="duplicate_email",
                )
            return email.lower()
        return email

    def clean(self):
        """
        Perform cross-field validation including security questions.
        """
        cleaned_data = super().clean()
        self.clean_security_questions()
        return cleaned_data

    def save(self, commit=True):
        """
        Save the user with auto-generated username, combined full_name,
        CUSTOMER role, and three hashed security question answers.

        Uses transaction.atomic() to ensure all-or-nothing save.
        """
        from django.db import transaction

        with transaction.atomic():
            # Create user instance without saving yet
            user = super().save(commit=False)

            # Set fields from cleaned_data
            first_name = self.cleaned_data.get("first_name", "")
            last_name = self.cleaned_data.get("last_name", "")
            user.username = generate_unique_username(first_name, last_name)
            user.full_name = f"{first_name} {last_name}".strip()

            # Assign CUSTOMER role by default
            user.role = CustomUser.Role.CUSTOMER

            if commit:
                user.save()

                # Create security question records with hashed answers
                questions = [
                    self.cleaned_data.get("security_question_1"),
                    self.cleaned_data.get("security_question_2"),
                    self.cleaned_data.get("security_question_3"),
                ]
                answers = [
                    self.cleaned_data.get("security_answer_1"),
                    self.cleaned_data.get("security_answer_2"),
                    self.cleaned_data.get("security_answer_3"),
                ]

                for question, answer in zip(questions, answers):
                    SecurityQuestion.objects.create(
                        user=user,
                        question=question,
                        hashed_answer=make_password(answer),
                    )

        return user


class ProfileEditForm(forms.ModelForm):
    """
    Form for editing user profile information.

    Allows users to update their full name, phone number, default delivery
    address, username, and profile picture. Email changes are intentionally excluded
    and require a separate re-verification flow.
    """

    remove_profile_picture = forms.BooleanField(
        label=_("Remove current photo"),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = CustomUser
        fields = [
            "full_name",
            "phone_number",
            "default_delivery_address",
            "username",
            "profile_picture",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter your full name",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+1 (555) 123-4567",
            }),
            "default_delivery_address": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Enter your default delivery address",
            }),
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Choose a username",
            }),
            "profile_picture": forms.FileInput(attrs={
                "class": "form-control",
                "accept": "image/jpeg,image/png,image/webp,image/gif"
            }),
        }
        labels = {
            "full_name": _("Full Name"),
            "phone_number": _("Phone Number"),
            "default_delivery_address": _("Default Delivery Address"),
            "username": _("Username"),
            "profile_picture": _("Profile Picture"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show remove checkbox only when editing existing user with photo
        if self.instance and self.instance.pk and self.instance.profile_picture:
            self.fields['remove_profile_picture'].widget.attrs.pop('disabled', None)
        else:
            self.fields['remove_profile_picture'].widget.attrs['disabled'] = 'disabled'
            self.fields['remove_profile_picture'].help_text = _("No photo to remove.")

    def clean_username(self):
        """
        Validate username:
        - Must not be empty
        - Must be lowercase
        - Must be unique
        """
        username = self.cleaned_data.get("username", "").strip().lower()

        if not username:
            raise forms.ValidationError(
                _("Username cannot be empty."),
                code="empty_username",
            )

        # Check uniqueness, excluding the current user
        existing = CustomUser.objects.filter(username__iexact=username)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                _("This username is already taken."),
                code="duplicate_username",
            )

        return username

    def clean_profile_picture(self):
        """Validate profile picture file type and size."""
        picture = self.cleaned_data.get("profile_picture")
        if picture:
            import os
            ext = os.path.splitext(picture.name)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                raise forms.ValidationError(
                    _("Only JPG, PNG, WebP, and GIF images are allowed."),
                    code="invalid_image_type",
                )
            # Check file size (max 5MB)
            if picture.size > 5 * 1024 * 1024:
                raise forms.ValidationError(
                    _("Image size must be less than 5MB."),
                    code="image_too_large",
                )
        return picture


class ChangeSecurityQuestionsForm(forms.Form):
    """
    Form for updating security questions.

    Requires the user's current password for verification.
    All three questions must be unique and all answers provided.
    Answers are hashed using Django's make_password.
    """

    current_password = forms.CharField(
        label=_("Current Password"),
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your current password",
        }),
    )
    security_question_1 = forms.TypedChoiceField(
        label=_("Security Question 1"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    security_answer_1 = forms.CharField(
        label=_("Answer 1"),
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your answer",
        }),
    )
    security_question_2 = forms.TypedChoiceField(
        label=_("Security Question 2"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    security_answer_2 = forms.CharField(
        label=_("Answer 2"),
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your answer",
        }),
    )
    security_question_3 = forms.TypedChoiceField(
        label=_("Security Question 3"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    security_answer_3 = forms.CharField(
        label=_("Answer 3"),
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your answer",
        }),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        """
        Verify the user's current password.
        """
        password = self.cleaned_data.get("current_password")
        if self.user and not self.user.check_password(password):
            raise forms.ValidationError(
                _("Incorrect password. Please try again."),
                code="wrong_password",
            )
        return password

    def clean(self):
        """
        Validate security questions:
        - All three must be selected
        - No duplicates
        - All answers provided
        """
        cleaned_data = super().clean()
        q1 = cleaned_data.get("security_question_1")
        q2 = cleaned_data.get("security_question_2")
        q3 = cleaned_data.get("security_question_3")
        a1 = cleaned_data.get("security_answer_1")
        a2 = cleaned_data.get("security_answer_2")
        a3 = cleaned_data.get("security_answer_3")

        if not q1 or not q2 or not q3:
            raise forms.ValidationError(
                _("Please select all three security questions."),
                code="missing_questions",
            )

        if len({q1, q2, q3}) != 3:
            raise forms.ValidationError(
                _("Please select three different security questions."),
                code="duplicate_questions",
            )

        if not a1 or not a2 or not a3:
            raise forms.ValidationError(
                _("Please provide answers for all three security questions."),
                code="missing_answers",
            )

        return cleaned_data

    def save(self):
        """
        Replace all existing security questions with new ones.
        Answers are hashed using Django's make_password.
        """
        from django.db import transaction

        with transaction.atomic():
            # Delete existing questions
            self.user.security_questions.all().delete()

            # Create new questions with hashed answers
            questions = [
                self.cleaned_data["security_question_1"],
                self.cleaned_data["security_question_2"],
                self.cleaned_data["security_question_3"],
            ]
            answers = [
                self.cleaned_data["security_answer_1"],
                self.cleaned_data["security_answer_2"],
                self.cleaned_data["security_answer_3"],
            ]

            for question, answer in zip(questions, answers):
                SecurityQuestion.objects.create(
                    user=self.user,
                    question=question,
                    hashed_answer=make_password(answer),
                )


class SecurityQuestionRecoveryForm(forms.Form):
    """
    Form for account recovery via security questions.

    Step 1: User enters their username.
    Step 2: User answers their three security questions.

    Uses Django's session to pass the verified user between steps.
    Answers are compared against hashed answers using check_password().
    """

    username = forms.CharField(
        label=_("Username"),
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your username",
                "autofocus": True,
            }
        ),
    )
    answer_1 = forms.CharField(
        label=_("Answer 1"),
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your answer",
            }
        ),
    )
    answer_2 = forms.CharField(
        label=_("Answer 2"),
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your answer",
            }
        ),
    )
    answer_3 = forms.CharField(
        label=_("Answer 3"),
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your answer",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user:
            self.fields.pop("username", None)

    def clean_username(self):
        """
        Verify that the username exists in the system.
        """
        username = self.cleaned_data.get("username")
        if username:
            try:
                self.user = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                raise forms.ValidationError(
                    _("No account found with this username."),
                    code="username_not_found",
                )
        return username

    def clean(self):
        """
        If username was submitted, this is step 1 - skip answer validation.
        If answers were submitted, validate them against the user's hashed answers.
        """
        cleaned_data = super().clean()

        if "username" in self.data:
            return cleaned_data

        if not self.user:
            return cleaned_data

        answer_1 = cleaned_data.get("answer_1", "").strip()
        answer_2 = cleaned_data.get("answer_2", "").strip()
        answer_3 = cleaned_data.get("answer_3", "").strip()

        questions = list(
            self.user.security_questions.all().order_by("id")
        )

        if len(questions) != 3:
            raise forms.ValidationError(
                _("Security questions are not properly configured for this account."),
                code="no_security_questions",
            )

        if not answer_1 or not answer_2 or not answer_3:
            raise forms.ValidationError(
                _("Please provide answers for all three security questions."),
                code="missing_answers",
            )

        if not check_password(answer_1, questions[0].hashed_answer):
            raise forms.ValidationError(
                _("One or more answers are incorrect. Please try again."),
                code="incorrect_answers",
            )

        if not check_password(answer_2, questions[1].hashed_answer):
            raise forms.ValidationError(
                _("One or more answers are incorrect. Please try again."),
                code="incorrect_answers",
            )

        if not check_password(answer_3, questions[2].hashed_answer):
            raise forms.ValidationError(
                _("One or more answers are incorrect. Please try again."),
                code="incorrect_answers",
            )

        return cleaned_data


class RecoveryPasswordResetForm(forms.Form):
    """
    Form for resetting password after successful security question recovery.

    Uses Django's built-in password validators to ensure strong passwords.
    """

    new_password1 = forms.CharField(
        label=_("New Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter a strong password",
                "autocomplete": "new-password",
            }
        ),
        help_text=_(
            "Your password must contain at least 8 characters, "
            "including uppercase, lowercase, and a digit."
        ),
    )
    new_password2 = forms.CharField(
        label=_("Confirm New Password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Re-enter your password",
                "autocomplete": "new-password",
            }
        ),
        help_text=_("Enter the same password as above, for verification."),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_new_password2(self):
        """
        Verify that the two password entries match.
        """
        password1 = self.cleaned_data.get("new_password1")
        password2 = self.cleaned_data.get("new_password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(
                _("The two password fields didn't match."),
                code="password_mismatch",
            )
        return password2

    def clean_new_password1(self):
        """
        Validate the new password using Django's password validators.
        """
        password1 = self.cleaned_data.get("new_password1")
        if self.user:
            validate_password(password1, self.user)
        return password1

    def save(self):
        """
        Set the user's new password.
        """
        password = self.cleaned_data["new_password1"]
        self.user.set_password(password)
        self.user.save()
        return self.user
