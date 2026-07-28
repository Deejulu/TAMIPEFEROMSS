"""
Forms for the admin dashboard.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from shop.models import Category, Product
from .models import SiteContent

User = get_user_model()


class UserEditForm(forms.ModelForm):
    """
    Form for editing user details by admin.
    
    Does not include password field - password changes should be done through
    the standard password reset flow.
    """
    
    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone_number', 'role', 'is_active']
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
            'is_active': _('Unchecking will deactivate the user account.'),
        }
    
    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        """
        Validate that admin doesn't lock themselves out.
        """
        cleaned_data = super().clean()
        
        # If editing the current logged-in user
        if self.request_user and self.instance.pk == self.request_user.pk:
            # Check if they're trying to deactivate themselves
            if not cleaned_data.get('is_active'):
                raise forms.ValidationError(
                    _("You cannot deactivate your own account.")
                )
            
            # Check if they're trying to demote themselves from SUPER_ADMIN
            if self.request_user.role == User.Role.SUPER_ADMIN:
                new_role = cleaned_data.get('role')
                if new_role != User.Role.SUPER_ADMIN:
                    # Check if there are other super admins
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


class UserCreateForm(forms.ModelForm):
    """
    Form for creating new users by admin.
    
    Includes password field for initial account creation.
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
    
    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone_number', 'role', 'is_active']
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
        """
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        
        if commit:
            user.save()
        
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
        fields = ['name', 'category', 'price', 'stock_quantity', 'image', 'description', 'is_active']
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

    def clean_category(self):
        category = self.cleaned_data.get('category')
        if not category:
            raise ValidationError(_("Please select a category."))
        return category


class SiteContentForm(forms.ModelForm):
    """
    Form for editing website content sections.
    """
    class Meta:
        model = SiteContent
        fields = ['section', 'title', 'content']
        widgets = {
            'section': forms.Select(attrs={
                'class': 'form-select'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Section title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10,
                'placeholder': 'Content for this section (HTML allowed)'
            }),
        }
        help_texts = {
            'section': _('Select which section of the website this content will appear on.'),
            'content': _('You can use HTML tags to format the content.'),
        }
