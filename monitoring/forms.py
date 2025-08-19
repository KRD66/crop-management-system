
from django import forms
from django.utils import timezone
from datetime import date, timedelta
from .models import Inventory, Crop, HarvestRecord
from django.db import models




class AddInventoryForm(forms.ModelForm):
    """Form for adding new inventory items"""
    
    class Meta:
        model = Inventory
        fields = ['crop', 'quantity_tons', 'storage_location', 'quality_grade', 'expiry_date', 'storage_condition', 'batch_number', 'unit_price', 'notes']
        widgets = {
            'crop': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'quantity_tons': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': '100',
                'min': '0.1',
                'step': '0.1',
                'required': True
            }),
            'storage_location': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Warehouse A',
                'required': True
            }),
            'quality_grade': forms.Select(attrs={
                'class': 'form-select',
                'required': True
            }),
            'expiry_date': forms.DateInput(attrs={
                'class': 'form-input',
                'type': 'date',
                'required': True
            }),
            'storage_condition': forms.Select(attrs={
                'class': 'form-select'
            }),
            'batch_number': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Batch ID (optional)'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-input',
                'placeholder': '0.00',
                'min': '0',
                'step': '0.01'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'placeholder': 'Additional notes (optional)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Only show active crops
        self.fields['crop'].queryset = Crop.objects.filter(is_active=True).order_by('name')
        
        # Set default expiry date (6 months from now)
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
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True,
            'id': 'remove_crop_select'
        }),
        empty_label="Select crop"
    )
    
    storage_location = forms.CharField(
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True,
            'id': 'remove_location_select'
        })
    )
    
    quantity_tons = forms.DecimalField(
        min_value=0.1,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-input',
            'placeholder': '100',
            'min': '0.1',
            'step': '0.1',
            'required': True
        })
    )
    
    reason = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Reason for removal (optional)'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        crops_with_stock = Inventory.objects.values('crop').distinct()
        crop_choices = []
        
        for item in crops_with_stock:
            crop = Crop.objects.get(id=item['crop'])
            total_quantity = Inventory.objects.filter(crop=crop).aggregate(
                total=models.Sum('quantity_tons')
            )['total'] or 0
            
            if total_quantity > 0:
                crop_choices.append((crop.id, f"{crop.name} ({total_quantity} tons available)"))
        
        self.fields['crop'].choices = [('', 'Select crop')] + crop_choices
    
    def clean(self):
        cleaned_data = super().clean()
        crop = cleaned_data.get('crop')
        storage_location = cleaned_data.get('storage_location')
        quantity_requested = cleaned_data.get('quantity_tons')
        
        if crop and storage_location and quantity_requested:
    
            available_inventory = Inventory.objects.filter(
                crop=crop,
                storage_location=storage_location
            ).aggregate(total=models.Sum('quantity_tons'))['total'] or 0
            
            if quantity_requested > available_inventory:
                raise forms.ValidationError(
                    f"Only {available_inventory} tons available for {crop.name} at {storage_location}"
                )
        
        return cleaned_data


class InventoryFilterForm(forms.Form):
    """Form for filtering inventory items"""
    
    STORAGE_LOCATION_CHOICES = [
        ('', 'All Locations'),
        ('Warehouse A', 'Warehouse A'),
        ('Warehouse B', 'Warehouse B'), 
        ('Warehouse C', 'Warehouse C'),
        ('Warehouse D', 'Warehouse D'),
        ('Warehouse E', 'Warehouse E'),
    ]
    
    STATUS_CHOICES = [
        ('', 'All Status'),
        ('good', 'Good'),
        ('expiring', 'Expiring Soon'),
        ('low_stock', 'Low Stock'),
        ('expired', 'Expired'),
    ]
    
    crop = forms.ModelChoiceField(
        queryset=Crop.objects.filter(is_active=True),
        required=False,
        empty_label="All Crops",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    storage_location = forms.ChoiceField(
        choices=STORAGE_LOCATION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    quality_grade = forms.ChoiceField(
        choices=[('', 'All Grades')] + HarvestRecord.QUALITY_GRADES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'})
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'})
    )


class BulkInventoryUpdateForm(forms.Form):
    """Form for bulk updating inventory items"""
    
    ACTION_CHOICES = [
        ('update_location', 'Update Storage Location'),
        ('update_condition', 'Update Storage Condition'),
        ('mark_expired', 'Mark as Expired'),
        ('reserve', 'Reserve Items'),
        ('unreserve', 'Unreserve Items'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    new_storage_location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input'})
    )
    
    new_storage_condition = forms.ChoiceField(
        choices=Inventory.STORAGE_CONDITIONS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    selected_items = forms.CharField(
        widget=forms.HiddenInput()
    )
    
    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        
        if action == 'update_location' and not cleaned_data.get('new_storage_location'):
            raise forms.ValidationError("New storage location is required for this action.")
        
        if action == 'update_condition' and not cleaned_data.get('new_storage_condition'):
            raise forms.ValidationError("New storage condition is required for this action.")
        
        return cleaned_data