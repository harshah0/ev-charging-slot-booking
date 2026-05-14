# Testing Workflow Guide

Comprehensive testing strategies for the EV Charging Slot Booking platform, including RBAC, dashboards, and payment functionality.

---

## Quick Start

### Prerequisites

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install development dependencies
pip install -r requirements.txt pytest pytest-cov

# Verify application runs
flask run
# Output: Running on http://127.0.0.1:5000
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_auth.py

# Run specific test
pytest tests/test_auth.py::test_login_success

# Run in verbose mode
pytest -v

# Stop on first failure
pytest -x

# Show print statements
pytest -s
```

---

## Manual Testing Workflow

### Phase 1: Authentication

**Objective:** Verify login, registration, and session management

**Test Cases:**

#### 1.1: User Registration
```
Steps:
1. Navigate to http://localhost:5000/auth/register
2. Enter valid credentials:
   - Username: testuser123
   - Password: SecurePass@123
   - Confirm: SecurePass@123
3. Click "Register"

Expected Results:
✓ Redirected to /dashboard
✓ Navbar shows username "testuser123"
✓ User has role="user" (not admin)
✓ Wallet balance shows ₹0.00
✓ Flash message: "Registration successful"

Validation:
- flask shell: User.query.filter_by(username='testuser123').first().role == 'user'
```

#### 1.2: Admin Registration (Manual)
```
Steps:
1. Register as normal user (step 1.1)
2. Direct database update (development only):
   flask shell
   >>> from models import User
   >>> user = User.query.filter_by(username='admin_test').first()
   >>> user.role = 'admin'
   >>> from extensions import db
   >>> db.session.commit()
3. Logout and login as admin_test

Expected Results:
✓ Dashboard redirects to /dashboard/admin
✓ Admin Dashboard displays instead of user dashboard
✓ "Admin Dashboard" button in navbar
```

#### 1.3: Login with Invalid Credentials
```
Steps:
1. Navigate to /auth/login
2. Enter:
   - Username: nonexistent
   - Password: wrongpass
3. Click "Login"

Expected Results:
✓ Stays on login page (no redirect)
✓ Flash message: "Invalid username or password"
✓ Navbar shows "Login" button (not authenticated)
```

#### 1.4: Session Persistence
```
Steps:
1. Login as testuser123
2. Navigate to /dashboard
3. Close browser completely (kill server process)
4. Restart server: flask run
5. Open http://localhost:5000/dashboard

Expected Results:
✓ Dashboard loads (session cookie valid)
✓ Username shown
✓ All data displayed
```

#### 1.5: Logout
```
Steps:
1. Login as testuser123
2. Click "Logout" button in navbar
3. Click "OK" to confirm logout

Expected Results:
✓ Redirected to /
✓ Navbar shows "Login" and "Register" buttons
✓ Session cleared
✓ Navigate to /dashboard → Redirected to login
```

---

### Phase 2: RBAC (Role-Based Access Control)

**Objective:** Verify role-based permissions and restrictions

**Test Cases:**

#### 2.1: User Cannot Access Admin Routes
```
Prerequisites:
- Logged in as regular user (role='user')

Steps:
1. Try to access /stations/new
2. Try to access /stations/1/edit
3. Try to access /stations/1/delete
4. Try to access /dashboard/admin

Expected Results:
✓ All requests redirected to /
✓ Flash message: "You don't have permission to access this resource"
✓ Regular dashboard loads instead

Validation:
- Browser DevTools: Check redirect Location header
- Flask logs: Verify admin_required decorator triggered
```

#### 2.2: Admin Can Access All Routes
```
Prerequisites:
- Logged in as admin user (role='admin')

Steps:
1. Navigate to /stations/new
2. Fill form and create station
3. Edit the station: /stations/<id>/edit
4. Update the station
5. Navigate to /dashboard
6. Verify Admin Dashboard loads

Expected Results:
✓ Station creation succeeds
✓ Station edit form loads
✓ Update succeeds
✓ Admin Dashboard displays with admin-specific stats
✓ Flash messages confirm actions
```

#### 2.3: Non-Authenticated Users Cannot Access Protected Routes
```
Steps:
1. Ensure not logged in (or logout)
2. Try to access:
   - /dashboard
   - /bookings
   - /payment/recharge
   - /payment/transactions

Expected Results:
✓ All requests redirected to /auth/login
✓ After login, redirected to original request (/dashboard)
```

#### 2.4: Admin Dashboard Shows Admin-Specific Content
```
Prerequisites:
- Logged in as admin

Steps:
1. Navigate to /dashboard
2. Inspect page content

Expected Results:
✓ Page title: "Operations Dashboard"
✓ Stats cards show:
  - Total Users
  - Total Stations
  - Total Bookings
  - Active Bookings
  - Slot Utilization %
✓ "Recent Bookings" table shows User + Station columns
✓ "Station Shortcuts" grid shows all stations with Edit buttons
✓ NO "My Bookings" or "Nearby Stations" (user-specific)
```

#### 2.5: User Dashboard Shows User-Specific Content
```
Prerequisites:
- Logged in as regular user

Steps:
1. Navigate to /dashboard
2. Inspect page content

Expected Results:
✓ Page title: "My Dashboard"
✓ Greeting: "Welcome back, [username]"
✓ Stats cards show:
  - Total Bookings (user's total)
  - Active Bookings (user's active only)
  - Nearby Stations
  - Wallet Balance
✓ "Active Bookings" section shows user's bookings only
✓ "Nearby Stations" panel shows relevant stations
✓ NO admin stats (users, stations count)
```

---

### Phase 3: Payment System - Wallet & Recharge

**Objective:** Verify wallet functionality and recharge flow

**Test Cases:**

#### 3.1: Wallet Display on Dashboard
```
Prerequisites:
- Logged in as regular user
- Created user with wallet_balance=100.00 (or manually set in DB)

Steps:
1. Navigate to /dashboard
2. Inspect wallet card

Expected Results:
✓ Wallet card shows: "Wallet Balance: ₹100.00"
✓ "Recharge" button visible and clickable
✓ Navbar shows wallet balance: "₹100.00" as clickable link
```

#### 3.2: Recharge Wallet - Happy Path
```
Prerequisites:
- User with wallet_balance=100.00

Steps:
1. Click "Recharge" button on dashboard
2. Navigate to /payment/recharge
3. Enter amount: 500
4. Observe cost summary (real-time update):
   - Amount to add: ₹500.00
   - New balance: ₹600.00
5. Click "Recharge Now"
6. Observe transaction

Expected Results:
✓ Form displays with all fields
✓ Cost summary updates in real-time as amount entered
✓ Flash message: "Recharge successful. New balance: ₹600.00"
✓ Redirected to /dashboard
✓ Wallet balance updated to ₹600.00
✓ Navbar wallet balance updated
```

#### 3.3: Recharge with Invalid Amounts
```
Prerequisites:
- User on /payment/recharge form

Steps:
1. Test minimum amount:
   - Enter: 0.50
   - Click "Recharge Now"
   Expected: ✓ Succeeds (₹0.50 is valid)

2. Test below minimum:
   - Enter: 0
   - Click "Recharge Now"
   Expected: Flash error, form re-renders

3. Test above maximum:
   - Enter: 100001
   - Click "Recharge Now"
   Expected: Flash error: "Amount must not exceed ₹100,000"

4. Test invalid format:
   - Enter: "abc"
   - Click "Recharge Now"
   Expected: Flash error: "Please enter a valid amount"

5. Test negative:
   - Enter: -100
   - Click "Recharge Now"
   Expected: Flash error: "Amount must be positive"
```

#### 3.4: Transaction History Display
```
Prerequisites:
- User with multiple transactions (recharges + bookings)

Steps:
1. Click wallet balance in navbar (or navigate to /payment/transactions)
2. Inspect transaction history page

Expected Results:
✓ Current balance card matches dashboard
✓ Total transactions count correct
✓ Total recharges sum calculated
✓ Total spent sum calculated
✓ Transaction table shows all entries:
  - Date/Time formatted correctly
  - Type badges: green for recharge, blue for booking
  - Descriptions show station names for bookings
  - Amounts: negative for debits (red), positive for credits (green)
  - Balance progression correct (each row balance >= previous or <= as appropriate)
✓ Status badges: green for completed, yellow for pending
```

#### 3.5: Transaction History - No Transactions
```
Prerequisites:
- New user with no transactions

Steps:
1. Navigate to /payment/transactions
2. Inspect page

Expected Results:
✓ Page loads
✓ Stats cards show:
  - Current Balance: ₹0.00
  - Total Transactions: 0
  - Total Recharges: ₹0.00
  - Total Spent: ₹0.00
✓ Transaction table shows: "No transactions yet. Recharge your wallet to get started."
✓ "Recharge" link visible in message
```

---

### Phase 4: Payment Integration - Booking with Deduction

**Objective:** Verify booking creation deducts wallet and creates transaction

**Test Cases:**

#### 4.1: Booking Cost Display (Pre-Confirmation)
```
Prerequisites:
- Logged in as user
- At least one charging station exists
- User has sufficient wallet balance (₹100)

Steps:
1. Click "Book a Station" or navigate to stations list
2. Click "Book" on any station
3. Form displays with cost summary
4. Enter charging duration: 60 minutes
5. Observe cost calculator updates

Expected Results:
✓ Cost summary section displays:
  - Base rate: ₹0.50 per minute
  - Duration: 60 minutes (updates as you type)
  - Estimated Cost: ₹30.00
  - Wallet Balance: ₹100.00
  - Balance After Booking: ₹70.00 (red if negative)
✓ Real-time calculation updates as duration changes
✓ If balance after < 0, text turns red
```

#### 4.2: Booking with Sufficient Balance
```
Prerequisites:
- User with wallet_balance=100.00
- Station with available_slots > 0

Steps:
1. Book station for 60 minutes (costs ₹30)
2. Click "Confirm Booking"
3. Observe transaction

Expected Results:
✓ Flash message: "Booking created successfully. Charged: ₹30.00. Remaining balance: ₹70.00"
✓ Redirected to /bookings/history
✓ Booking appears in history with status="confirmed"
✓ Navigate to /dashboard → Wallet shows ₹70.00
✓ Navigate to /payment/transactions → New transaction appears:
  - Type: Booking (blue badge)
  - Description: "[Station Name] for 60 minutes"
  - Amount: -₹30.00 (red)
  - Balance After: ₹70.00
  - Status: Completed (green badge)
```

#### 4.3: Booking with Insufficient Balance
```
Prerequisites:
- User with wallet_balance=10.00
- Station with available_slots > 0

Steps:
1. Navigate to station booking form
2. Enter charging duration: 60 minutes (costs ₹30)
3. Observe cost summary shows:
   - Estimated Cost: ₹30.00
   - Balance After: -₹20.00 (RED)
4. Click "Confirm Booking"

Expected Results:
✓ Booking creation FAILS
✓ Flash message: "Insufficient wallet balance. Required: ₹30.00, Available: ₹10.00"
✓ Redirected to /payment/recharge
✓ Wallet remains ₹10.00 (no deduction)
✓ No transaction record created
✓ Station available_slots unchanged (not decremented)
```

#### 4.4: Booking Deduction is Atomic
```
Prerequisites:
- User with wallet_balance=100.00
- Set up database constraint to trigger error on transaction insert

Steps:
1. Simulate transaction creation failure (modify routes/bookings.py to raise Exception after wallet deduction)
2. Create booking that would cost ₹30
3. Observe error handling

Expected Results:
✓ Booking creation fails
✓ Error message displayed: "An error occurred while creating your booking"
✓ Wallet remains ₹100.00 (rollback successful)
✓ No booking created
✓ No transaction created
✓ Station available_slots unchanged

Validation:
- Flask logs should show rollback
- Database query: Booking.query.count() unchanged
- Database query: Transaction.query.count() unchanged
```

#### 4.5: Multiple Rapid Bookings
```
Prerequisites:
- User with wallet_balance=100.00
- Multiple stations available

Steps:
1. Open station 1 booking form
2. Open station 2 booking form in new tab
3. In tab 1: Create booking for 30 minutes (₹15)
4. Click submit
5. Quickly switch to tab 2 and submit booking for 30 minutes (₹15)

Expected Results:
✓ Tab 1: Booking succeeds, wallet = ₹85.00
✓ Tab 2: Booking succeeds, wallet = ₹70.00
✓ Both bookings confirmed
✓ Both transactions recorded
✓ Total deducted: ₹30.00
✓ No double-deduction or race condition
```

---

### Phase 5: Station Management (CRUD)

**Objective:** Verify admin can create, read, update, delete stations with RBAC

**Test Cases:**

#### 5.1: Create Station (Admin Only)
```
Prerequisites:
- Logged in as admin

Steps:
1. Click "+ Add Station" button in navbar
2. Fill form:
   - Station Name: "Charging Hub Alpha"
   - Address: "123 Main Street"
   - City: "New York"
   - State: "NY"
   - Total Slots: 10
   - Available Slots: 10
   - Charging Type: "DC Fast Charging"
3. Click "Create Station"

Expected Results:
✓ Redirected to stations list
✓ Flash message: "Station created successfully"
✓ New station appears in list
✓ available_slots = 10 / total_slots = 10
```

#### 5.2: Create Station (User Cannot)
```
Prerequisites:
- Logged in as regular user

Steps:
1. Try to navigate to /stations/new

Expected Results:
✓ Redirected to /
✓ Flash message: "You don't have permission to access this resource"
```

#### 5.3: Edit Station
```
Prerequisites:
- Logged in as admin
- Station exists

Steps:
1. Click "Edit" button on station
2. Modify:
   - Station Name: "Charging Hub Alpha Updated"
   - Total Slots: 15
3. Click "Update Station"

Expected Results:
✓ Redirected to stations list
✓ Flash message: "Station updated successfully"
✓ Station details updated in list
```

#### 5.4: Delete Station
```
Prerequisites:
- Logged in as admin
- Station with no active bookings

Steps:
1. Click "Delete" button on station
2. Confirm deletion in modal

Expected Results:
✓ Flash message: "Station deleted successfully"
✓ Station removed from list
✓ Booking count for that station = 0
```

#### 5.5: Station Availability Updates After Booking
```
Prerequisites:
- Station with 5 available slots

Steps:
1. Login as user
2. Create booking for the station
3. Logout
4. Login as admin
5. Navigate to stations list

Expected Results:
✓ Station available_slots decreased to 4
✓ Progress bar shows 1/5 slots used
```

---

### Phase 6: Booking Management

**Objective:** Verify booking creation, cancellation, and history

**Test Cases:**

#### 6.1: Create Booking - Happy Path
```
Prerequisites:
- Logged in as user with sufficient wallet (₹100)
- Station available

Steps:
1. Navigate to stations
2. Click "Book" on station
3. Enter booking time: tomorrow at 10:00 AM
4. Enter duration: 60 minutes
5. Click "Confirm Booking"

Expected Results:
✓ Booking created with status="confirmed"
✓ Transaction created with type="booking", amount=-30
✓ Wallet deducted ₹30.00
✓ Station available_slots decreased by 1
✓ Redirected to /bookings/history
```

#### 6.2: Booking History Display
```
Prerequisites:
- User with multiple bookings (mix of confirmed/cancelled)

Steps:
1. Navigate to /bookings
2. Inspect table

Expected Results:
✓ All bookings displayed (confirmed and cancelled)
✓ Columns show: Station, Date, Duration, Status, Actions
✓ Status badges: green for confirmed, gray for cancelled
✓ Cancel button only on confirmed bookings
✓ Pagination works (if > 10 bookings)
```

#### 6.3: Cancel Booking
```
Prerequisites:
- User with confirmed booking

Steps:
1. Click "Cancel" on booking
2. Confirm cancellation

Expected Results:
✓ Booking status changed to "cancelled"
✓ Station available_slots increased by 1
✓ Flash message: "Booking cancelled successfully"
✓ Booking row shows status="cancelled"

Note: Refund NOT implemented yet (future enhancement)
```

#### 6.4: Cannot Book Duplicate Slot
```
Prerequisites:
- User has confirmed booking for station A

Steps:
1. Try to book same station A again
2. Fill booking form

Expected Results:
✓ Error: "You already have an active booking for this station"
✓ Booking form re-rendered
✓ No duplicate booking created
```

---

### Phase 7: Dashboard Views

**Objective:** Verify statistics accuracy and role-based display

**Test Cases:**

#### 7.1: User Dashboard Statistics
```
Prerequisites:
- Logged in as user with:
  - 5 total bookings (2 active, 3 cancelled)
  - ₹75.00 wallet balance
  - 3 nearby stations

Steps:
1. Navigate to /dashboard
2. Inspect stats cards

Expected Results:
✓ Total Bookings: 5
✓ Active Bookings: 2
✓ Nearby Stations: 3
✓ Wallet Balance: ₹75.00
✓ "Active Bookings" section shows 2 entries
✓ "Nearby Stations" section shows 3 entries
```

#### 7.2: Admin Dashboard Statistics
```
Prerequisites:
- Logged in as admin
- Database has:
  - 5 users (including admin)
  - 3 stations
  - 10 total bookings (6 confirmed, 4 cancelled)
  - 3 active bookings

Steps:
1. Navigate to /dashboard
2. Inspect stats cards

Expected Results:
✓ Total Users: 5
✓ Total Stations: 3
✓ Total Bookings: 10
✓ Active Bookings: 3
✓ Slot Utilization: Calculated correctly (active/total)
✓ "Recent Bookings" table shows latest 8 bookings
✓ "Station Shortcuts" shows all stations
```

#### 7.3: Dashboard Statistics are Real-Time
```
Prerequisites:
- Two browser windows: admin dashboard + stations management

Steps:
1. Window 1: Open admin dashboard
2. Window 2: Create new station
3. Window 1: Refresh page

Expected Results:
✓ Stats update: Total Stations incremented
✓ "Station Shortcuts" includes new station
```

---

### Phase 8: Map and Discovery

**Objective:** Verify station map and discovery features

**Test Cases:**

#### 8.1: Station Map Display
```
Prerequisites:
- Multiple stations with coordinates

Steps:
1. Click "View Map" on dashboard
2. Inspect map

Expected Results:
✓ Leaflet map loads
✓ All stations displayed as markers
✓ Markers show station name on hover
✓ Zoom and pan work
✓ Mobile responsive (fit to screen)
```

#### 8.2: Nearby Stations on Dashboard
```
Prerequisites:
- User has active booking at "New York"
- Multiple stations in New York and other cities

Steps:
1. User dashboard displays
2. Inspect "Nearby Stations" section

Expected Results:
✓ Shows stations in same city (NY)
✓ Or fallback to same state
✓ Or fallback to recently created
✓ Quick "Book" buttons functional
```

---

## Automated Testing

### Unit Tests

**File:** `tests/test_models.py`

```python
def test_user_role_enum():
    """Test UserRole enum values"""
    assert UserRole.ADMIN.value == 'admin'
    assert UserRole.USER.value == 'user'

def test_user_is_admin():
    """Test is_admin method"""
    admin = User(role='admin')
    user = User(role='user')
    assert admin.is_admin() == True
    assert user.is_admin() == False

def test_transaction_is_debit():
    """Test transaction debit/credit logic"""
    debit = Transaction(amount=Decimal('-30.00'))
    credit = Transaction(amount=Decimal('100.00'))
    assert debit.is_debit == True
    assert credit.is_credit == True
```

### Integration Tests

**File:** `tests/test_payment_integration.py`

```python
def test_booking_with_payment_deduction(app, client, auth, db):
    """Test complete booking flow with wallet deduction"""
    # Setup
    user = User(username='testuser', wallet_balance=Decimal('100.00'))
    db.session.add(user)
    db.session.commit()
    
    station = ChargingStation(
        station_name='Test Station',
        available_slots=10,
        total_slots=10
    )
    db.session.add(station)
    db.session.commit()
    
    # Login
    auth.login('testuser', 'password')
    
    # Create booking
    response = client.post('/bookings', data={
        'station_id': station.id,
        'booking_time': '2024-12-25T10:00',
        'charging_duration': 60,
        'csrf_token': get_csrf_token(response)
    })
    
    # Assertions
    assert response.status_code == 302
    user.refresh()
    assert user.wallet_balance == Decimal('70.00')
    
    booking = Booking.query.filter_by(user_id=user.id).first()
    assert booking is not None
    assert booking.booking_status == 'confirmed'
    
    transaction = Transaction.query.filter_by(booking_id=booking.id).first()
    assert transaction is not None
    assert transaction.amount == Decimal('-30.00')

def test_insufficient_balance_prevents_booking(app, client, auth, db):
    """Test booking fails with insufficient balance"""
    user = User(username='testuser', wallet_balance=Decimal('10.00'))
    db.session.add(user)
    db.session.commit()
    
    station = ChargingStation(available_slots=10, total_slots=10)
    db.session.add(station)
    db.session.commit()
    
    auth.login('testuser', 'password')
    
    response = client.post('/bookings', data={
        'station_id': station.id,
        'booking_time': '2024-12-25T10:00',
        'charging_duration': 60,  # Costs ₹30, wallet only has ₹10
        'csrf_token': get_csrf_token(response)
    })
    
    assert response.status_code == 302
    user.refresh()
    assert user.wallet_balance == Decimal('10.00')  # Unchanged
    assert Booking.query.count() == 0
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=routes --cov=models --cov=utils

# Run specific test file
pytest tests/test_payment_integration.py

# Run specific test function
pytest tests/test_payment_integration.py::test_booking_with_payment_deduction

# Stop on first failure
pytest -x

# Show print output
pytest -s
```

---

## Performance Testing

### Load Testing Bookings

**Objective:** Ensure payment system handles concurrent bookings

```bash
# Install load testing tool
pip install locust

# Create locustfile.py
cat > locustfile.py << 'EOF'
from locust import HttpUser, task, between

class BookingUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Login
        self.client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'password'
        })
    
    @task
    def create_booking(self):
        self.client.post('/bookings', data={
            'station_id': 1,
            'booking_time': '2024-12-25T10:00',
            'charging_duration': 60
        })
EOF

# Run load test
locust -f locustfile.py --host=http://localhost:5000 --users 50 --spawn-rate 5

# Open http://localhost:8089 and start test
```

### Database Query Performance

```bash
flask shell

# Enable query logging
>>> from extensions import db
>>> import logging
>>> logging.basicConfig()
>>> logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Run query
>>> from models import Transaction
>>> transactions = Transaction.query.filter_by(user_id=1).all()
# Observe SQL queries in console
# Should be 1 query (not N queries)
```

---

## Debugging Tools

### Flask Shell

```bash
flask shell

# Create test user
>>> from models import User
>>> from extensions import db
>>> from decimal import Decimal
>>> user = User(username='debug_user', password='test123')
>>> user.wallet_balance = Decimal('100.00')
>>> db.session.add(user)
>>> db.session.commit()

# Query transactions
>>> from models import Transaction
>>> txns = Transaction.query.filter_by(user_id=user.id).all()
>>> for t in txns:
...     print(f"{t.created_at}: {t.transaction_type} {t.amount} ({t.status})")

# Check station availability
>>> from models import ChargingStation
>>> station = ChargingStation.query.first()
>>> print(f"{station.available_slots}/{station.total_slots} slots available")
```

### Database Inspector

```bash
flask shell

>>> from extensions import db
>>> from sqlalchemy import inspect

# Get all tables
>>> inspector = inspect(db.engine)
>>> inspector.get_table_names()
['users', 'charging_stations', 'bookings', 'transactions', 'alembic_version']

# Get transactions table columns
>>> inspector.get_columns('transactions')

# Get foreign keys
>>> inspector.get_foreign_keys('transactions')

# Get indexes
>>> inspector.get_indexes('transactions')
```

### Browser DevTools

```
F12 → Network tab:
- Monitor /payment/recharge POST request
- Check request payload (amount, csrf_token)
- Verify response headers (Set-Cookie for session)
- Check response body (redirect location)

F12 → Console:
- Run JavaScript: document.getElementById('amount').value = 500
- Observe cost calculator updates
- Check for JavaScript errors

F12 → Application tab:
- Inspect session cookies
- View localStorage for flash messages
```

---

## Common Test Failures

### Issue: "CSRF token missing"
```
Cause: Form submission without csrf_token hidden field
Fix: Ensure template includes: <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

### Issue: "User not authenticated"
```
Cause: Test not logging in before protected route
Fix: Call auth.login() or client.post('/auth/login', data={...}) before
```

### Issue: "Station not found"
```
Cause: Test referencing station ID that doesn't exist
Fix: Create station first with ChargingStation() before booking test
```

### Issue: "Wallet balance unchanged"
```
Cause: Database not committing transaction
Fix: Ensure db.session.commit() called in route and user.refresh() called in test
```

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.10
      - run: pip install -r requirements.txt
      - run: flask db upgrade
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v2
```

---

## Testing Checklist

- [ ] All unit tests pass: `pytest tests/test_models.py`
- [ ] All integration tests pass: `pytest tests/test_payment_integration.py`
- [ ] All routes tested: GET, POST with valid and invalid data
- [ ] RBAC enforced: Admin-only routes reject non-admin users
- [ ] Payment system atomic: All-or-nothing transaction semantics
- [ ] Wallet validation works: Insufficient balance blocks booking
- [ ] Transaction history accurate: All transactions recorded with correct amounts
- [ ] Dashboard stats correct: Matches database queries
- [ ] No N+1 queries: Query logs show optimal queries
- [ ] Error handling tested: 400, 402, 403, 404, 500 cases
- [ ] Concurrency tested: Rapid bookings don't cause race conditions
- [ ] Performance acceptable: Page loads < 1 second
- [ ] Mobile responsive: All pages work on phone

---

## References

- [Pytest Documentation](https://docs.pytest.org/)
- [Flask Testing](https://flask.palletsprojects.com/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/testing.html)
- [Locust Load Testing](https://locust.io/)

---

## Support

For testing issues:
1. Review this guide
2. Check test output for specific error
3. Run test with `-s` flag to see print statements
4. Use Flask shell to debug database state
5. Review application logs
