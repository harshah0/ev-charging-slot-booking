"""Custom decorators for authorization and access control."""
from functools import wraps
from typing import Callable, TypeVar

from flask import flash, redirect, url_for
from flask_login import current_user

# Type variable for decorator functions
F = TypeVar("F", bound=Callable)


def admin_required(f: F) -> F:
    """
    Decorator to restrict route access to admin users only.
    
    Behavior:
    - If user not authenticated: redirects to login page
    - If user authenticated but not admin: shows error flash and redirects to home
    - If user is admin: allows access to route
    
    Usage:
        @app.route('/admin/manage')
        @admin_required
        def admin_panel():
            return render_template('admin.html')
    
    Security Note:
    - Always apply @admin_required BEFORE @login_required for cleaner error messages
    - For explicit layering: @admin_required wraps login_required checks internally
    - Authorization failures use 302 redirect, not 403 Forbidden (prevents info leakage)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check authentication (Flask-Login)
        if not current_user.is_authenticated:
            flash("You must be logged in to access this page.", "warning")
            return redirect(url_for("auth.login"))
        
        # Check authorization (admin role)
        if not current_user.is_admin():
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("home.home"))
        
        # User is authenticated and authorized
        return f(*args, **kwargs)
    
    return decorated_function
