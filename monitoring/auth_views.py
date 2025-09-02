# monitoring/auth_views.py - Updated Authentication Views (Login Only)
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
import json
from .forms import CustomLoginForm
from .models import UserProfile

class CustomLoginView(LoginView):
    """Custom login view for admin-added users only"""
    form_class = CustomLoginForm
    template_name = 'monitoring/auth.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('monitoring:dashboard')
    
    def dispatch(self, request, *args, **kwargs):
        # Simplified dispatch - let Django handle the redirect logic
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        user = form.get_user()
        
        # Check if user has UserProfile (admin-added users should have this)
        try:
            user_profile = user.userprofile
        except UserProfile.DoesNotExist:
            messages.error(self.request, 'Access denied. Only administrator-added users can log in.')
            return self.form_invalid(form)
        
        # Check if user is active
        if not user_profile.is_active:
            messages.error(self.request, 'Your account has been deactivated. Please contact your administrator.')
            return self.form_invalid(form)
        
        remember_me = form.cleaned_data.get('remember_me')
        if not remember_me:
            # Set session expiry to 0 seconds. So it will automatically close the session after the browser is closed.
            self.request.session.set_expiry(0)
            # Set session as modified to force data updates/cookie to be saved.
            self.request.session.modified = True
        
        messages.success(
            self.request, 
            f'Welcome back, {user.first_name or user.username}! Role: {user_profile.get_role_display()}'
        )
        return super().form_valid(form)
    
    def form_invalid(self, form):
        # Check if the error is due to invalid credentials
        if form.errors:
            # Try to get the user to provide more specific error message
            username = form.data.get('username', '').strip()
            if username:
                try:
                    from django.contrib.auth.models import User
                    user = User.objects.get(username=username) if '@' not in username else User.objects.get(email=username)
                    
                    # User exists but wrong password
                    messages.error(self.request, 'Invalid password. Please try again or contact your administrator.')
                except User.DoesNotExist:
                    # User doesn't exist
                    messages.error(self.request, 'User not found. Only administrator-added users can access this system.')
            else:
                messages.error(self.request, 'Please enter your username/email and password.')
        else:
            messages.error(self.request, 'Invalid username/email or password. Please try again.')
        
        return super().form_invalid(form)

class CustomLogoutView(LogoutView):
    """Custom logout view"""
    next_page = reverse_lazy('monitoring:login')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.success(request, 'You have been successfully logged out.')
        return super().dispatch(request, *args, **kwargs)


def login_view(request):
    """Custom login view function for admin-added users only"""
    
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            
            # Check if user has UserProfile (admin-added users should have this)
            try:
                user_profile = user.userprofile
            except UserProfile.DoesNotExist:
                messages.error(request, 'Access denied. Only administrator-added users can log in.')
                return render(request, 'monitoring/auth.html', {'form': form})
            
            # Check if user is active
            if not user_profile.is_active:
                messages.error(request, 'Your account has been deactivated. Please contact your administrator.')
                return render(request, 'monitoring/auth.html', {'form': form})
            
            remember_me = form.cleaned_data.get('remember_me', False)
            
            # Set session expiry based on remember_me
            if not remember_me:
                request.session.set_expiry(0)  # Session expires when browser closes
            
            login(request, user)
            
            messages.success(
                request, 
                f'Welcome back, {user.first_name or user.username}! Role: {user_profile.get_role_display()}'
            )
            
            # Redirect to dashboard
            next_page = request.GET.get('next', 'monitoring:dashboard')
            if next_page == 'monitoring:dashboard':
                return redirect('monitoring:dashboard')
            else:
                return redirect(next_page)
        else:
            # Handle form errors with more specific messages
            username = request.POST.get('username', '').strip()
            if username:
                try:
                    from django.contrib.auth.models import User
                    user = User.objects.get(username=username) if '@' not in username else User.objects.get(email=username)
                    
                    # User exists but wrong password or inactive
                    if not user.is_active:
                        messages.error(request, 'Your account is inactive. Please contact your administrator.')
                    else:
                        messages.error(request, 'Invalid password. Please try again.')
                except User.DoesNotExist:
                    # User doesn't exist
                    messages.error(request, 'User not found. Only administrator-added users can access this system.')
            else:
                messages.error(request, 'Please enter your username/email and password.')
    else:
        form = CustomLoginForm()
    
    return render(request, 'monitoring/auth.html', {'form': form})


def get_demo_accounts():
    """Get demo account information for display"""
    return {
        'admin': {
            'email': 'demo@harvestpro.com',
            'password': 'demo123',
            'role': 'Admin'
        }
    }


@csrf_exempt
def demo_login(request):
    """AJAX endpoint for demo account login"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            role = data.get('role', '').lower()
            
            demo_accounts = get_demo_accounts()
            
            if role == 'admin' and 'admin' in demo_accounts:
                account = demo_accounts['admin']
                user = authenticate(
                    request,
                    username=account['email'],
                    password=account['password']
                )
                
                if user:
                    # Check if user has UserProfile
                    try:
                        user_profile = user.userprofile
                        if not user_profile.is_active:
                            return JsonResponse({
                                'success': False,
                                'message': 'Demo account is deactivated.'
                            })
                    except UserProfile.DoesNotExist:
                        return JsonResponse({
                            'success': False,
                            'message': 'Demo account not properly configured.'
                        })
                    
                    login(request, user)
                    return JsonResponse({
                        'success': True,
                        'message': f'Logged in as {account["role"]}',
                        'redirect_url': reverse_lazy('monitoring:dashboard')
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Admin demo account not found. Please create demo accounts first.'
                    })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid demo role'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method'
    })


@staff_member_required
def create_demo_accounts():
    """Management command to create demo accounts - Only for staff/superusers"""
    from django.contrib.auth.models import User
    
    demo_users = [
        {
            'username': 'admin_demo',
            'email': 'demo@harvestpro.com',
            'password': 'demo123',
            'first_name': 'Admin',
            'last_name': 'Demo',
            'role': 'admin',
            'is_staff': True,
            'is_superuser': True
        }
    ]
    
    created_users = []
    for user_data in demo_users:
        user, created = User.objects.get_or_create(
            username=user_data['username'],
            defaults={
                'email': user_data['email'],
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name'],
                'is_staff': user_data.get('is_staff', False),
                'is_superuser': user_data.get('is_superuser', False)
            }
        )
        
        if created:
            user.set_password(user_data['password'])
            user.save()
            
            # Create UserProfile
            profile, profile_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': user_data['role'],
                    'is_active': True
                }
            )
            
            created_users.append(f"{user_data['username']} ({user_data['role']})")
    
    return created_users


# View to redirect registration attempts
def registration_disabled(request):
    """View to inform users that registration is disabled"""
    messages.info(
        request, 
        'User registration is disabled. Only administrators can create new accounts. '
        'Please contact your administrator if you need access.'
    )
    return redirect('monitoring:login')


# Custom decorator to check if user was added by admin
def admin_added_required(view_func):
    """Decorator to ensure user has UserProfile (was added by admin)"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('monitoring:login')
        
        try:
            user_profile = request.user.userprofile
            if not user_profile.is_active:
                messages.error(request, 'Your account has been deactivated.')
                return redirect('monitoring:login')
        except UserProfile.DoesNotExist:
            messages.error(request, 'Access denied. Invalid account.')
            return redirect('monitoring:login')
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


# Role-based permission checks
def role_required(allowed_roles):
    """Decorator to check user role"""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('monitoring:login')
            
            try:
                user_profile = request.user.userprofile
                if user_profile.role not in allowed_roles:
                    messages.error(request, 'You do not have permission to access this page.')
                    return redirect('monitoring:dashboard')  # FIXED: Added namespace
            except UserProfile.DoesNotExist:
                messages.error(request, 'Access denied. Invalid account.')
                return redirect('monitoring:login')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator