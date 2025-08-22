# monitoring/auth_views.py - Authentication Views
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .forms import CustomUserRegistrationForm, CustomLoginForm
from .models import UserProfile

class CustomLoginView(LoginView):
    """Custom login view"""
    form_class = CustomLoginForm
    template_name = 'registration/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        return reverse_lazy('monitoring:dashboard')
    
    def form_valid(self, form):
        remember_me = form.cleaned_data.get('remember_me')
        if not remember_me:
            # Set session expiry to 0 seconds. So it will automatically close the session after the browser is closed.
            self.request.session.set_expiry(0)
            # Set session as modified to force data updates/cookie to be saved.
            self.request.session.modified = True
        
        messages.success(self.request, f'Welcome back, {form.get_user().first_name or form.get_user().username}!')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Invalid username/email or password. Please try again.')
        return super().form_invalid(form)


class CustomLogoutView(LogoutView):
    """Custom logout view"""
    next_page = reverse_lazy('monitoring:login')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.success(request, 'You have been successfully logged out.')
        return super().dispatch(request, *args, **kwargs)


def register_view(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('monitoring:dashboard')
    
    if request.method == 'POST':
        form = CustomUserRegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                username = form.cleaned_data.get('username')
                messages.success(
                    request, 
                    f'Account created successfully for {username}! You can now log in.'
                )
                
                # Auto-login the user after registration
                user = authenticate(
                    username=user.username,
                    password=form.cleaned_data['password1']
                )
                if user:
                    login(request, user)
                    return redirect('monitoring:dashboard')
                else:
                    return redirect('monitoring:login')
                    
            except Exception as e:
                messages.error(request, f'Error creating account: {str(e)}')
        else:
            # Form has errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.title()}: {error}')
    else:
        form = CustomUserRegistrationForm()
    
    context = {
        'form': form,
        'demo_accounts': get_demo_accounts()
    }
    return render(request, 'registration/register.html', context)


def login_view(request):
    """Custom login view function"""
    if request.user.is_authenticated:
        return redirect('monitoring:dashboard')
    
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                
                # Handle remember me
                remember_me = form.cleaned_data.get('remember_me')
                if not remember_me:
                    request.session.set_expiry(0)
                
                # Get user role for welcome message
                role = 'User'
                if hasattr(user, 'userprofile'):
                    role = user.userprofile.get_role_display()
                
                messages.success(
                    request, 
                    f'Welcome back, {user.first_name or user.username}! ({role})'
                )
                
                # Redirect to next or dashboard
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('monitoring:dashboard')
            else:
                messages.error(request, 'Invalid credentials. Please try again.')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomLoginForm()
    
    context = {
        'form': form,
        'demo_accounts': get_demo_accounts()
    }
    return render(request, 'registration/login.html', context)


def get_demo_accounts():
    """Get demo account information for display"""
    return {
        'admin': {
            'email': 'demo@harvestpro.com',
            'password': 'demo123',
            'role': 'Admin'
        },
        'manager': {
            'email': 'manager@harvestpro.com', 
            'password': 'manager123',
            'role': 'Farm Manager'
        },
        'worker': {
            'email': 'worker@harvestpro.com',
            'password': 'worker123',
            'role': 'Field Worker'
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
            
            if role in demo_accounts:
                account = demo_accounts[role]
                user = authenticate(
                    request,
                    username=account['email'],
                    password=account['password']
                )
                
                if user:
                    login(request, user)
                    return JsonResponse({
                        'success': True,
                        'message': f'Logged in as {account["role"]}',
                        'redirect_url': reverse_lazy('monitoring:dashboard')
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Demo account not found. Please create demo accounts first.'
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


def create_demo_accounts():
    """Management command to create demo accounts"""
    from django.contrib.auth.models import User
    
    demo_users = [
        {
            'username': 'admin_demo',
            'email': 'demo@harvestpro.com',
            'password': 'demo123',
            'first_name': 'Admin',
            'last_name': 'Demo',
            'role': 'admin'
        },
        {
            'username': 'manager_demo',
            'email': 'manager@harvestpro.com',
            'password': 'manager123',
            'first_name': 'Manager',
            'last_name': 'Demo',
            'role': 'farm_manager'
        },
        {
            'username': 'worker_demo',
            'email': 'worker@harvestpro.com',
            'password': 'worker123',
            'first_name': 'Worker',
            'last_name': 'Demo',
            'role': 'field_worker'
        }
    ]
    
    created_users = []
    for user_data in demo_users:
        user, created = User.objects.get_or_create(
            username=user_data['username'],
            defaults={
                'email': user_data['email'],
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name']
            }
        )
        
        if created:
            user.set_password(user_data['password'])
            user.save()
            
            # Create UserProfile
            profile, profile_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': user_data['role']}
            )
            
            created_users.append(f"{user_data['username']} ({user_data['role']})")
    
    return created_users