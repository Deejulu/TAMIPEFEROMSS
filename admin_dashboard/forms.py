"""
Forms for the admin dashboard.
"""
import os
import bleach
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password

from shop.models import Category, Product
from farm_management.models import Batch
from accounts.models import SecurityQuestion
from accounts.constants import SECURITY_QUESTIONS
from accounts.utils import generate_unique_username_with_id, split_full_name
from .models import SiteContent, BusinessHours

User = get_user_model()


class UserEditForm(forms.ModelForm):
    """
    Form for editing user details by admin.
    
    Does not include password field - password changes should be done through
    the standard password reset flow.
    """
    
    profile_picture = forms.ImageField(
        label=_("Profile Photo"),
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/png,image/webp,image/gif'
        }),
        help_text=_("JPG, PNG, WebP or GIF. Max 5MB. Leave blank to keep existing photo."),
    )
    
    remove_profile_picture = forms.BooleanField(
        label=_("Remove current photo"),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    
    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone_number', 'role', 'is_active', 'profile_picture']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone Number (optional)'
            }),
            'role': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        help_texts = {
            'role': _('Changing role affects user permissions and access levels.'),
            'is_active': _('Unchecking this will deactivate the user account.'),
        }
    
    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        # Show remove checkbox only when editing existing user with photo
        if self.instance and self.instance.pk and self.instance.profile_picture:
            self.fields['remove_profile_picture'].widget.attrs.pop('disabled', None)
        else:
            self.fields['remove_profile_picture'].widget.attrs['disabled'] = 'disabled'
            self.fields['remove_profile_picture'].help_text = _("No photo to remove.")
    
    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture:
            ext = os.path.splitext(picture.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                raise forms.ValidationError(
                    _("Only JPG, PNG, WebP and GIF images are allowed."),
                    code="invalid_image_type",
                )
            if picture.size > 5 * 1024 * 1024:
                raise forms.ValidationError(
                    _("Image size must be less than 5MB."),
                    code="image_too_large",
                )
        return picture
    
    def clean(self):
        cleaned_data = super().clean()
        
        # If editing the current logged-in user
        if self.request_user and self.instance.pk == self.request_user.pk:
            if not cleaned_data.get('is_active'):
                raise forms.ValidationError(
                    _("You cannot deactivate your own account.")
                )
            
            if self.request_user.role == User.Role.SUPER_ADMIN:
                new_role = cleaned_data.get('role')
                if new_role != User.Role.SUPER_ADMIN:
                    other_super_admins = User.objects.filter(
                        role=User.Role.SUPER_ADMIN,
                        is_active=True
                    ).exclude(pk=self.instance.pk).count()
                    
                    if other_super_admins == 0:
                        raise forms.ValidationError(
                            _("You cannot change your role as you are the only active Super Admin. "
                              "Promote another user to Super Admin first.")
                        )
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        remove_photo = self.cleaned_data.get('remove_profile_picture')
        
        if remove_photo and user.profile_picture:
            user.profile_picture.delete(save=False)
            user.profile_picture = None
        
        if commit:
            user.save()
            self.save_m2m()
        
        return user


class UserCreateForm(forms.ModelForm):
    """
    Form for creating new users by admin.
    
    Includes password field for initial account creation.
    When role is Customer, email becomes optional and security questions are required.
    """
    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        }),
        help_text=_("Password must be at least 8 characters.")
    )
    password2 = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm Password'
        }),
        help_text=_("Enter the same password for verification.")
    )

    # Security question fields (required for Customer role)
    security_question_1 = forms.TypedChoiceField(
        label=_("Security Question 1"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    security_answer_1 = forms.CharField(
        label=_("Answer 1"),
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your answer"
        }),
        required=False,
    )
    security_question_2 = forms.TypedChoiceField(
        label=_("Security Question 2"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    security_answer_2 = forms.CharField(
        label=_("Answer 2"),
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your answer"
        }),
        required=False,
    )
    security_question_3 = forms.TypedChoiceField(
        label=_("Security Question 3"),
        choices=[("", "---------")] + SECURITY_QUESTIONS,
        coerce=str,
        empty_value="",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )
    security_answer_3 = forms.CharField(
        label=_("Answer 3"),
        max_length=255,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your answer"
        }),
        required=False,
    )
    
    profile_picture = forms.ImageField(
        label=_("Profile Photo"),
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/png,image/webp,image/gif'
        }),
        help_text=_("JPG, PNG, WebP or GIF. Max 5MB."),
    )
    
    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone_number', 'role', 'is_active', 'profile_picture']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone Number (optional)'
            }),
            'role': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        help_texts = {
            'email': _('User will use this email to log in. Required for admin/staff accounts.'),
            'role': _('Determines user permissions and access levels.'),
            'is_active': _('Inactive users cannot log in.'),
        }
    
    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        # Make email not required by default - will be enforced in clean()
        self.fields['email'].required = False
    
    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture:
            ext = os.path.splitext(picture.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                raise forms.ValidationError(
                    _("Only JPG, PNG, WebP and GIF images are allowed."),
                    code="invalid_image_type",
                )
            if picture.size > 5 * 1024 * 1024:
                raise forms.ValidationError(
                    _("Image size must be less than 5MB."),
                    code="image_too_large",
                )
        return picture
    
    def clean(self):
        """
        Validate role restrictions, security questions, and passwords.

        - Super Staff may only create STAFF accounts (never SUPER_STAFF or
          SUPER_ADMIN). Super Admin may create any role.
        - Email is required for non-Customer roles.
        - Security questions are required for Customer role.
        - A password is required for Staff/Super Staff roles (and must be
          strong and match). Customer accounts without a password get a
          placeholder instead.
        """
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        email = cleaned_data.get('email')
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        request_user = getattr(self, 'request_user', None)
        if (
            request_user
            and request_user.role == User.Role.SUPER_STAFF
            and role in (User.Role.SUPER_STAFF, User.Role.SUPER_ADMIN)
        ):
            raise forms.ValidationError(
                _("Super Staff can only create Staff accounts."),
                code="super_staff_role_restricted",
            )

        # Email is required for non-Customer roles
        if role and role != User.Role.CUSTOMER and not email:
            raise forms.ValidationError(
                _("Email address is required for admin and staff accounts."),
                code="email_required_for_admin",
            )

        # Staff / Super Staff roles require a password
        if role and role != User.Role.CUSTOMER:
            if not password1:
                raise forms.ValidationError(
                    _("Password is required for staff accounts."),
                    code="password_required",
                )
            if password1 != password2:
                raise forms.ValidationError(
                    _("The two password fields didn't match."),
                    code="password_mismatch",
                )
            try:
                validate_password(password1)
            except forms.ValidationError as exc:
                self.add_error('password1', exc)

        # Security questions are required for Customer role
        if role == User.Role.CUSTOMER:
            q1 = cleaned_data.get('security_question_1')
            q2 = cleaned_data.get('security_question_2')
            q3 = cleaned_data.get('security_question_3')
            a1 = cleaned_data.get('security_answer_1')
            a2 = cleaned_data.get('security_answer_2')
            a3 = cleaned_data.get('security_answer_3')

            if not q1 or not q2 or not q3:
                raise forms.ValidationError(
                    _("Please select all three security questions for Customer accounts."),
                    code="missing_security_questions",
                )

            if len({q1, q2, q3}) != 3:
                raise forms.ValidationError(
                    _("Please select three different security questions."),
                    code="duplicate_security_questions",
                )

            if not a1 or not a2 or not a3:
                raise forms.ValidationError(
                    _("Please provide answers for all three security questions."),
                    code="missing_security_answers",
                )

        return cleaned_data
    
    def clean_password2(self):
        """
        Validate that passwords match.
        """
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("The two password fields must match."))
        
        return password2
    
    def clean_password1(self):
        """
        Validate password strength.
        """
        password = self.cleaned_data.get('password1')
        
        if len(password) < 8:
            raise forms.ValidationError(_("Password must be at least 8 characters long."))
        
        return password
    
    def save(self, commit=True):
        """
        Save the user with hashed password.
        For Customer role without email, generate a placeholder email.
        """
        from django.db import transaction
        
        with transaction.atomic():
            user = super().save(commit=False)
            user.set_password(self.cleaned_data['password1'])
            
            # Auto-generate username from full_name if not provided
            full_name = self.cleaned_data.get('full_name', '')
            if full_name and not user.username:
                first_name, last_name = split_full_name(full_name)
                user.username, user.account_id = generate_unique_username_with_id(
                    first_name, last_name
                )
            
            # For Customer role without email, generate placeholder
            if user.role == User.Role.CUSTOMER and not user.email:
                user.email = f"{user.username}@tamipee.com"
            
            if commit:
                user.save()
                
                # Create security question records for Customer role
                if user.role == User.Role.CUSTOMER:
                    questions = [
                        self.cleaned_data.get('security_question_1'),
                        self.cleaned_data.get('security_question_2'),
                        self.cleaned_data.get('security_question_3'),
                    ]
                    answers = [
                        self.cleaned_data.get('security_answer_1'),
                        self.cleaned_data.get('security_answer_2'),
                        self.cleaned_data.get('security_answer_3'),
                    ]
                    
                    for question, answer in zip(questions, answers):
                        if question and answer:
                            SecurityQuestion.objects.create(
                                user=user,
                                question=question,
                                hashed_answer=make_password(answer),
                            )
        
        return user


class StaffCreateForm(forms.ModelForm):
    """
    Form for creating new Staff or Super Staff accounts.
    Super Admin can assign both STAFF and SUPER_STAFF roles.
    Super Staff can only assign STAFF role.
    """
    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        }),
        help_text=_("Password must be at least 8 characters."),
    )
    password2 = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm Password'
        }),
        help_text=_("Enter the same password for verification."),
    )

    profile_picture = forms.ImageField(
        label=_("Profile Photo"),
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/png,image/webp,image/gif'
        }),
        help_text=_("JPG, PNG, WebP or GIF. Max 5MB."),
    )

    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone_number', 'role', 'is_active', 'profile_picture']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone Number (optional)'
            }),
            'role': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        help_texts = {
            'email': _('Required. User will use this email to log in.'),
            'role': _('Determines user permissions and access levels.'),
            'is_active': _('Inactive users cannot log in.'),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        
        # Restrict role choices based on who is creating
        if self.request_user and self.request_user.role == User.Role.SUPER_STAFF:
            self.fields['role'].choices = [
                (User.Role.STAFF, User.Role.STAFF.label),
            ]

    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture:
            ext = os.path.splitext(picture.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                raise forms.ValidationError(
                    _("Only JPG, PNG, WebP and GIF images are allowed."),
                    code="invalid_image_type",
                )
            if picture.size > 5 * 1024 * 1024:
                raise forms.ValidationError(
                    _("Image size must be less than 5MB."),
                    code="image_too_large",
                )
        return picture

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("The two password fields must match."))
        return password2

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if len(password) < 8:
            raise forms.ValidationError(_("Password must be at least 8 characters long."))
        return password

    def save(self, commit=True):
        from django.db import transaction
        
        with transaction.atomic():
            user = super().save(commit=False)
            user.set_password(self.cleaned_data['password1'])
            first_name, last_name = split_full_name(self.cleaned_data.get('full_name', ''))
            user.username, user.account_id = generate_unique_username_with_id(
                first_name, last_name
            )
            if commit:
                user.save()
        return user


class StaffEditForm(forms.ModelForm):
    """
    Form for editing Staff or Super Staff accounts.
    Super Admin can edit any staff account.
    Super Staff can only edit regular Staff accounts.
    """
    profile_picture = forms.ImageField(
        label=_("Profile Photo"),
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/png,image/webp,image/gif'
        }),
        help_text=_("JPG, PNG, WebP or GIF. Max 5MB. Leave blank to keep existing photo."),
    )
    
    remove_profile_picture = forms.BooleanField(
        label=_("Remove current photo"),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    
    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone_number', 'role', 'is_active', 'profile_picture']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email Address'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phone Number (optional)'
            }),
            'role': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        help_texts = {
            'email': _('User will use this email to log in.'),
            'role': _('Determines user permissions and access levels.'),
            'is_active': _('Inactive users cannot log in.'),
        }

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        
        # Restrict role choices based on who is editing
        if self.request_user and self.request_user.role == User.Role.SUPER_STAFF:
            self.fields['role'].choices = [
                (User.Role.STAFF, User.Role.STAFF.label),
            ]
        else:
            # Super Admin can assign STAFF or SUPER_STAFF
            self.fields['role'].choices = [
                (User.Role.STAFF, User.Role.STAFF.label),
                (User.Role.SUPER_STAFF, User.Role.SUPER_STAFF.label),
            ]
        
        # Show remove checkbox only when editing existing user with photo
        if self.instance and self.instance.pk and self.instance.profile_picture:
            self.fields['remove_profile_picture'].widget.attrs.pop('disabled', None)
        else:
            self.fields['remove_profile_picture'].widget.attrs['disabled'] = 'disabled'
            self.fields['remove_profile_picture'].help_text = _("No photo to remove.")

    def clean_profile_picture(self):
        picture = self.cleaned_data.get('profile_picture')
        if picture:
            ext = os.path.splitext(picture.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                raise forms.ValidationError(
                    _("Only JPG, PNG, WebP and GIF images are allowed."),
                    code="invalid_image_type",
                )
            if picture.size > 5 * 1024 * 1024:
                raise forms.ValidationError(
                    _("Image size must be less than 5MB."),
                    code="image_too_large",
                )
        return picture

    def clean(self):
        cleaned_data = super().clean()
        
        # Super Staff cannot edit Super Staff or Super Admin
        if self.request_user and self.request_user.role == User.Role.SUPER_STAFF:
            if self.instance.role in (User.Role.SUPER_STAFF, User.Role.SUPER_ADMIN):
                raise forms.ValidationError(
                    _("You do not have permission to edit this user.")
                )
        
        # Prevent editing self to change role
        if self.request_user and self.instance.pk == self.request_user.pk:
            if self.instance.role == User.Role.SUPER_STAFF:
                new_role = cleaned_data.get('role')
                if new_role != User.Role.SUPER_STAFF:
                    other_super_staff = User.objects.filter(
                        role=User.Role.SUPER_STAFF,
                        is_active=True
                    ).exclude(pk=self.instance.pk).count()
                    if other_super_staff == 0:
                        raise forms.ValidationError(
                            _("You cannot change your role as you are the only active Super Staff. "
                              "Promote another user to Super Staff first.")
                        )
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        remove_photo = self.cleaned_data.get('remove_profile_picture')
        
        if remove_photo and user.profile_picture:
            user.profile_picture.delete(save=False)
            user.profile_picture = None
        
        if commit:
            user.save()
            self.save_m2m()
        
        return user


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Category name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description'
            }),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'category', 'price', 'stock_quantity', 'image', 'description', 'is_active', 'linked_batch']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Product name'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'stock_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'linked_batch': forms.Select(attrs={
                'class': 'form-select'
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['linked_batch'].queryset = Batch.objects.all().order_by('-start_date')
        self.fields['linked_batch'].empty_label = 'No linked batch'

    def save(self, commit=True):
        instance = super().save(commit=False)
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'name'):
            from accounts.utils import optimize_image
            optimized = optimize_image(image, max_size=(1200, 1200), quality=85)
            instance.image = optimized
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class SiteContentForm(forms.ModelForm):
    """
    Form for editing website content sections.
    For the business_hours section, renders per-day time pickers
    instead of a rich text editor.
    """
    class Meta:
        model = SiteContent
        fields = [
            'section',
            'title',
            'content',
            'facebook_url',
            'instagram_url',
            'twitter_url',
            'tiktok_url',
            'whatsapp_url',
        ]
        widgets = {
            'section': forms.Select(attrs={
                'class': 'form-select'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Section title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control rich-text-editor',
                'rows': 10,
                'placeholder': 'Content for this section (HTML allowed)'
            }),
            'facebook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.facebook.com/yourpage',
            }),
            'instagram_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.instagram.com/yourpage',
            }),
            'twitter_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://x.com/yourpage',
            }),
            'tiktok_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.tiktok.com/@yourpage',
            }),
            'whatsapp_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://wa.me/2348012345678',
            }),
        }
        help_texts = {
            'section': _('Select which section of the website this content will appear on.'),
            'content': _('Use the rich text editor to format content. Only safe formatting tags are allowed.'),
        }

    # Per-day business hours fields
    monday_open = forms.TimeField(
        label=_("Monday open"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    monday_close = forms.TimeField(
        label=_("Monday close"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    monday_is_closed = forms.BooleanField(
        label=_("Monday closed"),
        required=False,
    )
    tuesday_open = forms.TimeField(
        label=_("Tuesday open"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    tuesday_close = forms.TimeField(
        label=_("Tuesday close"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    tuesday_is_closed = forms.BooleanField(
        label=_("Tuesday closed"),
        required=False,
    )
    wednesday_open = forms.TimeField(
        label=_("Wednesday open"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    wednesday_close = forms.TimeField(
        label=_("Wednesday close"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    wednesday_is_closed = forms.BooleanField(
        label=_("Wednesday closed"),
        required=False,
    )
    thursday_open = forms.TimeField(
        label=_("Thursday open"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    thursday_close = forms.TimeField(
        label=_("Thursday close"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    thursday_is_closed = forms.BooleanField(
        label=_("Thursday closed"),
        required=False,
    )
    friday_open = forms.TimeField(
        label=_("Friday open"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    friday_close = forms.TimeField(
        label=_("Friday close"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    friday_is_closed = forms.BooleanField(
        label=_("Friday closed"),
        required=False,
    )
    saturday_open = forms.TimeField(
        label=_("Saturday open"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    saturday_close = forms.TimeField(
        label=_("Saturday close"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    saturday_is_closed = forms.BooleanField(
        label=_("Saturday closed"),
        required=False,
    )
    sunday_open = forms.TimeField(
        label=_("Sunday open"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    sunday_close = forms.TimeField(
        label=_("Sunday close"),
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
    )
    sunday_is_closed = forms.BooleanField(
        label=_("Sunday closed"),
        required=False,
    )
    business_hours_notes = forms.CharField(
        label=_("Notes"),
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('Special hours, holiday notices, or other remarks'),
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['content'].required = False

        # Hide business hours fields by default
        self._show_business_hours_fields = False
        if self.instance and self.instance.section == 'business_hours':
            self._show_business_hours_fields = True
            # Hide the content field for business hours
            self.fields['content'].widget = forms.HiddenInput()
            # Populate initial values from existing BusinessHours record
            if self.instance.business_hours_detail:
                bh = self.instance.business_hours_detail
                for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                    self.fields[f'{day}_open'].initial = getattr(bh, f'{day}_open')
                    self.fields[f'{day}_close'].initial = getattr(bh, f'{day}_close')
                    self.fields[f'{day}_is_closed'].initial = getattr(bh, f'{day}_is_closed')
                self.fields['business_hours_notes'].initial = bh.notes

    def clean(self):
        cleaned_data = super().clean()
        section = cleaned_data.get('section')

        if section == 'business_hours':
            # For business hours, content is not required
            cleaned_data.pop('content', None)
        elif section != 'social_media' and not cleaned_data.get('content', '').strip():
            self.add_error('content', _('Content is required for this section.'))

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        if instance.section == 'business_hours' and commit:
            bh, created = BusinessHours.objects.get_or_create(site_content=instance)

            for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
                setattr(bh, f'{day}_open', self.cleaned_data.get(f'{day}_open'))
                setattr(bh, f'{day}_close', self.cleaned_data.get(f'{day}_close'))
                setattr(bh, f'{day}_is_closed', self.cleaned_data.get(f'{day}_is_closed', False))

            bh.notes = self.cleaned_data.get('business_hours_notes', '')
            bh.save()

        if commit:
            instance.save()

        return instance

    class Media:
        css = {
            'all': ('admin_dashboard/css/admin_dashboard.css',)
        }


class DeliveryOptionForm(forms.ModelForm):
    class Meta:
        from .models import DeliveryOption

        model = DeliveryOption
        fields = ["code", "enabled", "price", "estimated_days", "notes"]
        widgets = {
            "code": forms.Select(attrs={"class": "form-select"}),
            "enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "step": "0.01"}
            ),
            "estimated_days": forms.NumberInput(
                attrs={"class": "form-control", "min": "1"}
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
