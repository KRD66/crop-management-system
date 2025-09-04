# monitoring/context_processors.py

def role_permissions(request):
    """
    Injects role-based permissions into all templates.
    """
    # Default (for non-authenticated users)
    permissions = {
        "can_manage_farms": False,
        "can_manage_inventory": False,
        "can_generate_reports": False,
        "can_view_analytics": False,
        "can_track_harvests": False,
        "can_view_notifications": False,
        "can_manage_users": False,
    }

    if request.user.is_authenticated:
        try:
            role = request.user.userprofile.role  # assuming you store roles here

            if role == "admin":
                permissions = {key: True for key in permissions}  # all True

            elif role == "inventory_manager":
                permissions.update({
                    "can_manage_inventory": True,
                    "can_generate_reports": True,
                    "can_view_notifications": True,
                })

            elif role == "farm_manager":
                permissions.update({
                    "can_manage_farms": True,
                    "can_manage_inventory": True,
                    "can_generate_reports": True,
                    "can_view_analytics": True,
                    "can_track_harvests": True,
                    "can_view_notifications": True,
                })

            elif role == "field_supervisor":
                permissions.update({
                    "can_track_harvests": True,
                    "can_view_analytics": True,
                    "can_view_notifications": True,
                })

            elif role == "field_worker":
                permissions.update({
                    "can_track_harvests": True,
                    "can_view_notifications": True,
                })

        except Exception:
            pass  # if user has no profile yet, just keep defaults

    return permissions
