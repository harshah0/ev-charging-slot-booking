# Role-Based Access Control (RBAC) Architecture

## Overview

The EV Charging Slot Booking System implements a production-grade RBAC system with two roles: **admin** and **user**. This document explains the architecture, design patterns, and security best practices.

---

## 1. RBAC Architecture

### Role Hierarchy

```
┌─────────────────┐
│   All Users     │
├─────────────────┤
│   Role: user    │ ◄──── Default role for new registrations
│   Role: admin   │ ◄──── Elevated permissions
└─────────────────┘
```

### User Roles and Permissions

| Role | Can Create Stations | Can Edit Stations | Can Delete Stations | Can Book Slots | Can Cancel Own Bookings | Can View Stations |
|------|:-------------------:|:------------------:|:-------------------:|:---------------:|:----------------------:|:------------------:|
| **user** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **admin** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 2. Implementation Details

### Data Model: User Role Storage

```python
# models/user.py
class UserRole(str, Enum):
    """User role enumeration for role-based access control."""
    ADMIN = "admin"
    USER = "user"

class User(UserMixin, db.Model):
    role = db.Column(
        db.String(20),
        nullable=False,
        default=UserRole.USER.value,
        server_default=UserRole.USER.value,
        index=True,  # Indexed for efficient role-based queries
    )

    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == UserRole.ADMIN.value

    def is_user(self) -> bool:
        """Check if user has user role."""
        return self.role == UserRole.USER.value
```

**Key Design Decisions:**
- Role stored as string VARCHAR(20) with enum validation at application layer
- Server-side default ensures role always present, even if app bug skips assignment
- Index on role column enables efficient filtering (e.g., "find all admins for notifications")
- Utility methods (`is_admin()`, `is_user()`) encapsulate role checking logic for maintainability

### Authorization Decorator

```python
# utils/decorators.py
def admin_required(f: F) -> F:
    """
    Decorator to restrict route access to admin users only.
    
    Behavior:
    - Unauthenticated users → redirect to login
    - Authenticated non-admins → flash error + redirect to home
    - Admin users → proceed to route
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("You must be logged in to access this page.", "warning")
            return redirect(url_for("auth.login"))
        
        if not current_user.is_admin():
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("home.home"))
        
        return f(*args, **kwargs)
    
    return decorated_function
```

**Security Pattern:**
- **Layered Checks**: Authentication (is user logged in?) → Authorization (does user have permission?)
- **Fail Secure**: Rejects access by default; only allows specific authorized actions
- **Information Hiding**: Uses 302 redirect instead of 403 Forbidden to avoid revealing admin routes
- **User Feedback**: Flash messages explain why access denied (improve UX without leaking security info)

### Route Protection

```python
# routes/stations.py
from utils.decorators import admin_required

@stations_bp.get("/new")
@admin_required  # Only admins can create stations
def new_station():
    return render_template("stations/form.html", ...)

@stations_bp.post("")
@admin_required
def create_station():
    # Validate and create station
    ...

@stations_bp.get("/<int:station_id>/edit")
@admin_required
def edit_station(station_id: int):
    station = ChargingStation.query.get_or_404(station_id)
    return render_template("stations/form.html", station=station, ...)

@stations_bp.post("/<int:station_id>/update")
@admin_required
def update_station(station_id: int):
    # Validate and update station
    ...

@stations_bp.post("/<int:station_id>/delete")
@admin_required
def delete_station(station_id: int):
    # Delete station with safeguards
    ...

# Public routes: non-protected, accessible by all
@stations_bp.get("")
def list_stations():
    # Show all stations to anyone
    ...

@stations_bp.get("/map")
def station_map():
    # Interactive map accessible to anyone
    ...
```

**Route Protection Hierarchy:**
- **Tier 1 (Public)**: `list_stations()`, `station_map()` → no decorators
- **Tier 2 (Authenticated Users)**: `bookings.new_booking()`, `bookings.cancel()` → `@login_required`
- **Tier 3 (Admins Only)**: Station CRUD → `@admin_required`

---

## 3. Authentication vs Authorization

### Authentication: "Who are you?"

Authentication verifies **identity**. In this system:
- User provides username + password
- System validates credentials and creates session
- `current_user` populated via Flask-Login
- Decorator: `@login_required` (from Flask-Login)

```python
@app.route("/dashboard")
@login_required  # Blocks unauthenticated users
def dashboard():
    user_name = current_user.username  # Verified identity
    return render_template("dashboard.html", user_name=user_name)
```

### Authorization: "What are you allowed to do?"

Authorization verifies **permissions**. In this system:
- Session confirms user is authenticated
- System checks user's role
- Allows/denies access to resources based on role
- Decorator: `@admin_required` (custom)

```python
@app.route("/admin/manage-stations")
@admin_required  # Blocks non-admin authenticated users
def admin_panel():
    # Only admin users reach here
    stations = ChargingStation.query.all()
    return render_template("admin/stations.html", stations=stations)
```

### Why Both Matter

```
Scenario 1: Unauthenticated User tries to access admin route
   @login_required fails first
   → Redirect to login (prevent unauthorized access)

Scenario 2: Authenticated NORMAL User tries to access admin route
   @admin_required checks authentication (passes)
   Then checks role (fails)
   → Redirect to home with "permission denied" message (prevent unauthorized access)

Scenario 3: Authenticated ADMIN User tries to access admin route
   @admin_required checks authentication (passes)
   Then checks role (passes)
   → Execute route logic
```

---

## 4. Route-Level Protection Matters

### Why Protect at Route Level (Not Just UI)

**WRONG APPROACH: UI-Only Protection**
```jinja2
{# ❌ BAD: Hiding button in template doesn't protect the route #}
{% if current_user.is_admin() %}
  <a href="{{ url_for('admin.create_station') }}">Create Station</a>
{% endif %}
```

**Problem:** User can bypass UI by:
1. Modifying HTML in browser
2. Using browser DevTools to make direct API calls
3. Crafting HTTP requests with `curl` or Postman
4. Reviewing page source to find route URLs

**CORRECT APPROACH: Route-Level Protection**
```python
# ✅ GOOD: Route itself enforces permission
@app.route("/admin/create-station", methods=["POST"])
@admin_required
def create_station():
    # Even if attacker bypasses UI, route blocks non-admins
    # No permission = no resource created
```

### Defense in Depth

```
Layer 1: Route-level authorization (@admin_required)
   ↓ (If bypassed, attacker still can't access database)
Layer 2: Explicit model-level checks (optional: verify role in business logic)
   ↓ (If bypassed, database constraints prevent bad data)
Layer 3: Database constraints (NOT NULL role, FK validation)
```

**Best Practice:** Always protect at **all three layers** for critical operations:

```python
@app.route("/admin/delete-user/<int:user_id>", methods=["POST"])
@admin_required  # Layer 1: Route-level
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)
    
    # Layer 2: Explicit check (defensive programming)
    if not current_user.is_admin():
        abort(403)
    
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("admin.users"))
```

---

## 5. Security Best Practices

### 1. **Never Trust Client Input**

```python
# ❌ BAD: Trust user's role selection from form
@app.route("/register", methods=["POST"])
def register():
    role = request.form.get("role", "user")  # User could send "admin"!
    user = User(username=..., email=..., role=role)
    db.session.add(user)
    ...

# ✅ GOOD: Always set to default, never read from user input
@app.route("/register", methods=["POST"])
def register():
    user = User(
        username=...,
        email=...,
        role=UserRole.USER.value  # Hardcoded default, not from form
    )
    db.session.add(user)
    ...
```

### 2. **Fail Secure (Default Deny)**

```python
# ❌ BAD: Assumes everyone is allowed unless explicitly rejected
def can_delete_station(user, station):
    if user.role == "user":
        return False  # Only blocked for users
    return True  # Everyone else allowed (dangerous!)

# ✅ GOOD: Only allows explicit authorized roles
def can_delete_station(user, station):
    return user.role == "admin"  # Only admins allowed
```

### 3. **Minimize Information Leakage**

```python
# ❌ BAD: Admin route reveals admin URL via 403 error
@app.route("/admin/stats")
@admin_required  # Might return 403 "Access Forbidden"
def admin_stats():
    ...
# Attacker learns: "/admin/stats" exists and requires admin

# ✅ GOOD: Same redirect for both missing page and permission denied
@app.route("/admin/stats")
@admin_required  # Returns 302 redirect to home (attacker unsure if route exists)
def admin_stats():
    ...
```

### 4. **Use Role-Based Enums (Not Strings)**

```python
# ❌ BAD: Magic strings prone to typos
if user.role == "adminn":  # Typo not caught until runtime
    ...

# ✅ GOOD: Enum catches typos at development time
from models.user import UserRole

if user.role == UserRole.ADMIN.value:  # Enum autocomplete + type checking
    ...
```

### 5. **Audit Permission Changes**

```python
# ✅ GOOD: Log when admin role granted/revoked
user.role = UserRole.ADMIN.value
db.session.commit()
app.logger.warning(
    f"User {user.username} role changed to admin by {current_user.username}",
    extra={"user_id": user.id, "changed_by": current_user.id}
)
```

### 6. **Combine CSRF Protection with Authorization**

```python
# ✅ GOOD: Both auth AND CSRF protection
@app.route("/stations/<int:station_id>/delete", methods=["POST"])
@admin_required  # Authorization
def delete_station(station_id: int):
    if not validate_csrf_token(request.form.get("csrf_token")):
        # CSRF protection (prevents form forgery attacks)
        flash("Session expired. Please try again.", "danger")
        return redirect(...)
    
    # Delete logic here
    ...
```

### 7. **Explicit vs Implicit Permissions**

```python
# ✅ GOOD: Explicit permission model (readable, maintainable)
def is_authorized_to_edit_booking(user, booking):
    # User can edit their own booking
    if user.id == booking.user_id:
        return True
    # Admin can edit any booking
    if user.is_admin():
        return True
    return False

# Use in route:
@app.route("/bookings/<int:booking_id>/edit", methods=["POST"])
@login_required
def edit_booking(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)
    if not is_authorized_to_edit_booking(current_user, booking):
        abort(403)
    # Edit logic here
    ...
```

---

## 6. Database Migration

The migration adds the `role` column to the `users` table:

```sql
-- Migration: a7b2c4d5e6f7_add_role_column_to_users.py

-- Upgrade
ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user';
CREATE INDEX ix_users_role ON users(role);

-- Downgrade
DROP INDEX ix_users_role;
ALTER TABLE users DROP COLUMN role;
```

**To apply migration:**
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows

# Run migration
flask db upgrade

# Verify
flask shell
>>> from models.user import User
>>> user = User.query.first()
>>> user.role
'user'
```

---

## 7. Frontend Role Visibility

### Navbar Admin Controls

```jinja2
{# templates/base.html #}
{% if current_user.is_authenticated and current_user.is_admin() %}
  <a href="{{ url_for('stations.new_station') }}" class="btn btn-warning btn-sm">
    + Add Station
  </a>
{% endif %}
```

### Station List Admin Actions

```jinja2
{# templates/stations/list.html #}
{% if current_user.is_authenticated and current_user.is_admin() %}
  <a href="{{ url_for('stations.edit_station', station_id=station.id) }}"
     class="btn btn-sm btn-outline-secondary">Edit</a>
  <form method="post" action="{{ url_for('stations.delete_station', station_id=station.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button type="submit" class="btn btn-sm btn-outline-danger">Delete</button>
  </form>
{% endif %}
```

**Important:** UI conditionals are for **UX**, not security. Always protect routes with decorators.

---

## 8. Future Extensions

### Granular Permissions (When Needed)

```python
# Example: If you need more roles in future
class UserRole(str, Enum):
    SUPERADMIN = "superadmin"  # Full system access
    ADMIN = "admin"             # Station management
    OPERATOR = "operator"       # View-only access
    USER = "user"               # Regular user
```

### Permission Matrix

```python
PERMISSIONS = {
    "view_stations": ["user", "admin", "operator"],
    "create_stations": ["admin"],
    "edit_stations": ["admin"],
    "delete_stations": ["admin"],
    "create_bookings": ["user", "admin"],
    "view_system_stats": ["admin"],
}

def can_perform(user_role: str, action: str) -> bool:
    return user_role in PERMISSIONS.get(action, [])
```

---

## 9. Testing RBAC

### Unit Test Example

```python
# tests/test_rbac.py
def test_non_admin_cannot_create_station(client, user):
    """Normal user should not access station creation."""
    response = client.get("/stations/new")
    assert response.status_code == 302  # Redirect
    assert response.location.endswith("/")  # Redirects to home

def test_admin_can_create_station(client, admin_user):
    """Admin user should access station creation."""
    response = client.get("/stations/new")
    assert response.status_code == 200  # OK
    assert b"Station Name" in response.data  # Form renders
```

---

## 10. Summary

| Concept | Implementation | Security Impact |
|---------|----------------|-----------------| 
| **Role Storage** | VARCHAR(20) with enum | Prevents role injection |
| **Route Protection** | `@admin_required` decorator | Blocks unauthorized access |
| **UI Visibility** | Jinja2 conditionals | Improves UX (not security) |
| **Default Deny** | New users get "user" role | Fails secure |
| **Audit** | Logger on role changes | Tracks unauthorized attempts |
| **Layered Checks** | Auth + AuthZ decorators | Defense in depth |

---

## Questions & Troubleshooting

**Q: Can users change their own role to admin?**
A: No. Role changes only in database, never from user input. Only database/admin access allows role changes.

**Q: Why redirect instead of 403 Forbidden?**
A: To avoid leaking information about admin routes. Same redirect for "missing route" and "permission denied" confuses attackers.

**Q: How to safely promote user to admin?**
A: Database update + audit log:
```python
user = User.query.get(user_id)
user.role = UserRole.ADMIN.value
db.session.commit()
app.logger.warning(f"User {user.username} promoted to admin by {current_user.username}")
```

**Q: Can @admin_required work with other decorators?**
A: Yes! Apply in order (most restrictive first):
```python
@app.route("/admin/manage")
@admin_required  # First (most restrictive)
@csrf_protect    # Second
def admin_manage():  # Third (route logic)
    ...
```
