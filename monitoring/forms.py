# monitoring/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from django.db import models
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Inventory, Crop, HarvestRecord, UserProfile


# -------------------- AUTHENTICATION & USER MANAGEMENT --------------------

class CustomLoginForm(AuthenticationForm):
    """Custom login form that accepts email or username, with remember_me"""

    username = forms.CharField(
        label='Email / Username',
        max_length=254,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email or username',
            'autofocus': True,
        })
    )

    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        })
    )

    remember_me = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username:
            return username

        username = username.strip().lower()
        if '@' in username:
            try:
                user = User.objects.get(email__iexact=username)
                return user.username
            except User.DoesNotExist:
                pass
        return username

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise ValidationError("This account is inactive.")
        try:
            if not user.userprofile.is_active:
                raise ValidationError("Your account has been deactivated. Contact administrator.")
        except UserProfile.DoesNotExist:
            raise ValidationError("Access denied. Only administrator-added users can log in.")


class AdminUserCreationForm(forms.ModelForm):
    """Form for administrators to create new users"""

    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    username = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password1 = forms.CharField(label='Password', strip=False, widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label='Confirm Password', strip=False, widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, required=True, widget=forms.Select(attrs={'class': 'form-control'}))
    phone_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    is_active = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('A user with this email already exists.')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise ValidationError('A user with this username already exists.')
        return username

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') != cleaned.get('password2'):
            raise ValidationError("The two password fields didn't match.")
        if cleaned.get('password1') and len(cleaned.get('password1')) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.is_active = self.cleaned_data.get('is_active', True)
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                phone_number=self.cleaned_data.get('phone_number', ''),
                is_active=self.cleaned_data.get('is_active', True),
            )
        return user


class UserProfileUpdateForm(forms.ModelForm):
    """Form to update user profile and basic user information"""

    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, required=True, widget=forms.Select(attrs={'class': 'form-control'}))
    phone_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    is_active = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    class Meta:
        model = UserProfile
        fields = ('role', 'phone_number', 'is_active')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if self.user and User.objects.filter(email=email).exclude(pk=self.user.pk).exists():
            raise ValidationError('A user with this email already exists.')
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit and self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            self.user.email = self.cleaned_data['email']
            self.user.is_active = self.cleaned_data.get('is_active', True)
            self.user.save()
            profile.save()
        return profile


class PasswordResetRequestForm(forms.Form):
    """Form for users to request password reset (admin only)"""

    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

    def clean_email(self):
        email = self.cleaned_data.get('email')
        try:
            user = User.objects.get(email=email)
            if not hasattr(user, 'userprofile'):
                raise ValidationError('No account found with this email address.')
        except User.DoesNotExist:
            raise ValidationError('No account found with this email address.')
        return email


# -------------------- INVENTORY MANAGEMENT --------------------

class AddInventoryForm(forms.ModelForm):
    """Form for adding new inventory items"""

    class Meta:
        model = Inventory
        fields = ['crop', 'quantity_tons', 'storage_location', 'quality_grade',
                  'expiry_date', 'storage_condition', 'batch_number', 'unit_price', 'notes']
        widgets = {
            'crop': forms.Select(attrs={'class': 'form-select'}),
            'quantity_tons': forms.NumberInput(attrs={'class': 'form-input', 'min': '0.1', 'step': '0.1'}),
            'storage_location': forms.TextInput(attrs={'class': 'form-input'}),
            'quality_grade': forms.Select(attrs={'class': 'form-select'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'storage_condition': forms.Select(attrs={'class': 'form-select'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-input'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-input', 'min': '0', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['crop'].queryset = Crop.objects.filter(is_active=True).order_by('name')
        if not self.instance.pk:
            self.fields['expiry_date'].initial = date.today() + timedelta(days=180)

    def save(self, commit=True):
        inventory = super().save(commit=False)
        if self.user:
            inventory.managed_by = self.user
        inventory.date_stored = date.today()
        if commit:
            inventory.save()
        return inventory


class RemoveInventoryForm(forms.Form):
    """Form for removing inventory items"""

    crop = forms.ModelChoiceField(
        queryset=Crop.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="Select crop",
    )
    storage_location = forms.CharField(widget=forms.Select(attrs={'class': 'form-select'}))
    quantity_tons = forms.DecimalField(min_value=0.1, decimal_places=2, widget=forms.NumberInput(attrs={'class': 'form-input'}))
    reason = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-input'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        crops_with_stock = Inventory.objects.values('crop').distinct()
        crop_choices = []
        for item in crops_with_stock:
            crop = Crop.objects.get(id=item['crop'])
            total_quantity = Inventory.objects.filter(crop=crop).aggregate(total=models.Sum('quantity_tons'))['total'] or 0
            if total_quantity > 0:
                crop_choices.append((crop.id, f"{crop.name} ({total_quantity} tons available)"))
        self.fields['crop'].choices = [('', 'Select crop')] + crop_choices

    def clean(self):
        cleaned = super().clean()
        crop = cleaned.get('crop')
        storage_location = cleaned.get('storage_location')
        qty_requested = cleaned.get('quantity_tons')
        if crop and storage_location and qty_requested:
            available = Inventory.objects.filter(crop=crop, storage_location=storage_location).aggregate(
                total=models.Sum('quantity_tons'))['total'] or 0
            if qty_requested > available:
                raise forms.ValidationError(f"Only {available} tons available for {crop.name} at {storage_location}")
        return cleaned


class InventoryFilterForm(forms.Form):
    """Form for filtering inventory items"""

    STORAGE_LOCATION_CHOICES = [
        ('', 'All Locations'),
        ('Warehouse A', 'Warehouse A'),
        ('Warehouse B', 'Warehouse B'),
        ('Warehouse C', 'Warehouse C'),
    ]
    STATUS_CHOICES = [
        ('', 'All Status'),
        ('good', 'Good'),
        ('expiring', 'Expiring Soon'),
        ('low_stock', 'Low Stock'),
        ('expired', 'Expired'),
    ]

    crop = forms.ModelChoiceField(queryset=Crop.objects.filter(is_active=True), required=False, empty_label="All Crops")
    storage_location = forms.ChoiceField(choices=STORAGE_LOCATION_CHOICES, required=False)
    quality_grade = forms.ChoiceField(choices=[('', 'All Grades')] + HarvestRecord.QUALITY_GRADES, required=False)
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))


class BulkInventoryUpdateForm(forms.Form):
    """Form for bulk updating inventory items"""

    ACTION_CHOICES = [
        ('update_location', 'Update Storage Location'),
        ('update_condition', 'Update Storage Condition'),
        ('mark_expired', 'Mark as Expired'),
    ]

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    new_storage_location = forms.CharField(required=False)
    new_storage_condition = forms.ChoiceField(choices=Inventory.STORAGE_CONDITIONS, required=False)
    selected_items = forms.CharField(widget=forms.HiddenInput())

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        if action == 'update_location' and not cleaned.get('new_storage_location'):
            raise forms.ValidationError("New storage location is required.")
        if action == 'update_condition' and not cleaned.get('new_storage_condition'):
            raise forms.ValidationError("New storage condition is required.")
        return cleaned
