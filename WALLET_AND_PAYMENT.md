# Wallet and Payment Simulation System

## Overview

The wallet system is a production-ready payment simulation framework for the EV Charging Slot Booking platform. It provides:
- User wallet management with recharge functionality
- Automatic booking cost deduction
- Complete transaction history and audit trail
- Atomic database operations for financial consistency
- Role-based access to payment features

---

## Architecture

### Data Model

#### Transaction Model (`models/transaction.py`)
Records all wallet activity with financial audit trail:

```python
class Transaction(db.Model):
    id: int                    # Primary key
    user_id: int               # FK to users table
    booking_id: int            # FK to bookings (optional, for booking charges)
    transaction_type: str      # 'recharge', 'booking', 'refund'
    amount: Decimal(10,2)      # Positive for credit, negative for debit
    status: str                # 'completed', 'pending', 'failed'
    description: str           # Human-readable detail
    balance_after: Decimal     # Wallet balance post-transaction (audit snapshot)
    created_at: DateTime       # Timestamp (indexed for performance)
```

**Key Design Decisions:**
- `amount` is positive for recharges, negative for bookings (intuitive sign logic)
- `balance_after` snapshot prevents recalculation/audit discrepancies
- Indexes on `user_id`, `transaction_type`, `status`, `created_at` for efficient queries
- `booking_id` optional to support future refunds without requiring booking

---

## Features

### 1. User Wallet Balance

**Location:** User model (`wallet_balance` field already exists)
- Stored as `Numeric(10,2)` for precision
- Always non-negative (validated)
- Updated atomically when bookings/recharges occur

**Navbar Display:**
Wallet balance shown as clickable link in navbar header:
```jinja2
<a href="{{ url_for('payment.transaction_history') }}" class="btn btn-outline-light btn-sm">
  ₹{{ "%.2f"|format(current_user.wallet_balance) }}
</a>
```

---

### 2. Recharge Wallet Flow

**Route:** `POST /payment/recharge` (routes/payment.py)

**UI:** Responsive Bootstrap form (templates/payment/recharge.html)
- Amount input (₹1 - ₹100,000)
- Current balance display
- Booking rate display (₹0.50/min)
- Real-time balance calculator
- Success/failure flash messages

**Process:**
1. User enters recharge amount
2. CSRF validation
3. Amount validation (positive, within limits)
4. User wallet balance incremented
5. Transaction record created with type=`recharge`
6. Database committed atomically
7. Flash success message with new balance

**Error Handling:**
- Invalid amount format → 400 error
- Amount ≤ 0 → 400 error
- Amount > ₹100,000 → 400 error
- Database failure → 500 + rollback + error message

---

### 3. Booking Cost Deduction

**Integration Point:** `POST /bookings` (routes/bookings.py)

**Cost Calculation:**
```python
booking_cost = calculate_booking_cost(charging_duration_minutes)
# Formula: duration (min) × ₹0.50 = cost
```

**Booking with Payment Process:**
1. Station slot availability checked (existing logic)
2. Booking cost calculated based on charging_duration
3. Wallet balance validated (`validate_wallet_balance`)
4. Wallet deducted atomically
5. Booking created and flushed (gets ID)
6. Transaction record created with booking_id reference
7. Database committed in single transaction
8. Flash message shows amount deducted and remaining balance

**Insufficient Balance Handling:**
- User redirected to recharge page
- Flash message shows required amount and current balance
- User can recharge and retry

**Atomic Transaction Safety:**
```python
try:
    # All operations in single transaction
    booking = Booking(...)
    current_user.wallet_balance -= booking_cost
    db.session.add(booking)
    db.session.flush()  # Get booking ID
    transaction = Transaction(booking_id=booking.id, ...)
    db.session.add(transaction)
    db.session.commit()  # Single atomic commit
except Exception as e:
    db.session.rollback()  # Rolls back all changes
    flash("Error", "danger")
```

---

### 4. Transaction History Page

**Route:** `GET /payment/transactions` (routes/payment.py)

**Template:** `templates/payment/transactions.html`

**Displays:**
- Current wallet balance (card)
- Total transactions count (card)
- Total recharges (card)
- Total spent on bookings (card)
- Transaction detail table with columns:
  - Date & Time
  - Transaction Type (badge: recharge=green, booking=blue)
  - Description (station name + duration for bookings)
  - Amount (negative for debit, positive for credit)
  - Balance After (wallet state post-transaction)
  - Status (badge: completed=green, pending=yellow)

**Query Optimization:**
- Single query with no N+1 issues
- Ordered by `created_at DESC` for most recent first
- Relationships loaded via `joinedload` where needed

**Financial Audit Trail:**
- All transactions immutable (no edit/delete)
- Balance snapshots prevent recalculation errors
- Complete history from account creation

---

### 5. Dashboard Integration

#### User Dashboard (templates/dashboard/user.html)
- **Wallet Balance Card:** Displays current balance with "Recharge" button
- **Quick Actions:** Transactions link added to header
- Uses `current_user.wallet_balance` for real-time display

#### Booking Form (templates/bookings/new.html)
- **Cost Summary:** Shows estimated charge before confirmation
  - Base rate display
  - Duration entered by user
  - Real-time cost calculation (JavaScript)
  - Wallet balance before booking
  - Predicted balance after booking (red if negative)
- **JavaScript Calculator:** Dynamic cost update on duration change

---

## Pricing Configuration

**File:** `utils/payment.py`

```python
BASE_RATE_PER_MINUTE = Decimal("0.50")  # ₹0.50 per minute

def calculate_booking_cost(charging_duration_minutes: int) -> Decimal:
    """Example: 60 min × ₹0.50 = ₹30.00"""
```

**To Change Pricing:**
1. Update `BASE_RATE_PER_MINUTE` in `utils/payment.py`
2. All calculations automatically use new rate (no database changes needed)
3. Future bookings use new rate, past transactions show historical rates (in description)

---

## Transactional Integrity

### Why Atomic Operations Matter

**Problem:** Booking created but wallet not deducted = financial inconsistency

**Solution:** Single database transaction wraps all operations:
```
START TRANSACTION
  1. Create booking
  2. Deduct from wallet
  3. Create transaction record
COMMIT (all succeed) or ROLLBACK (all fail)
```

**Key Patterns:**

1. **Row-Level Locks (Station):**
   ```python
   station = db.session.query(ChargingStation).with_for_update().one_or_none()
   # Prevents race condition: two users booking last slot simultaneously
   ```

2. **Flush Before Create:**
   ```python
   db.session.add(booking)
   db.session.flush()  # Get booking.id without committing
   transaction.booking_id = booking.id
   ```

3. **Try/Except with Rollback:**
   ```python
   try:
       db.session.commit()
   except Exception:
       db.session.rollback()
       flash("Error", "danger")
   ```

### Financial Consistency Guarantees

| Scenario | Guarantee |
|----------|-----------|
| Booking created, wallet deducted | ✅ Both succeed |
| Booking creation fails | ✅ Wallet unchanged (rollback) |
| Wallet deduction fails | ✅ Booking unchanged (rollback) |
| Database crash mid-transaction | ✅ Neither change applied |
| User cancels booking | ⚠️ No refund (future feature) |

---

## Query Optimization

### No N+1 Query Issues

```python
# ✅ GOOD: Joins loaded upfront
transactions = (
    Transaction.query
    .options(joinedload(Transaction.booking))
    .filter_by(user_id=current_user.id)
    .all()
)
# Single query returns all data

# ❌ BAD: Lazy loading in loop
for transaction in transactions:
    booking = transaction.booking  # Separate query per iteration!
```

### Efficient Dashboard Queries

```python
# Aggregations use COUNT/SUM at database level (not Python loop)
total_recharges = db.session.query(
    func.coalesce(func.sum(Transaction.amount), 0)
).filter(Transaction.transaction_type == "recharge").scalar()
# Returns single number, not rows
```

---

## Security Considerations

### Wallet Balance Validation

```python
is_valid, error_msg = validate_wallet_balance(
    wallet_balance=user.wallet_balance,
    required_amount=booking_cost
)
```

- Prevents overspending
- User-friendly error message
- Server-side validation (never trust client)

### Amount Formatting

```python
# ✅ GOOD: Always round to 2 decimal places
amount = round(Decimal(amount_str), 2)

# ❌ BAD: Float arithmetic loses precision
amount = float(amount_str) * 100 / 100  # Precision loss
```

### CSRF Protection

All payment operations require CSRF tokens:
```jinja2
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

---

## Migration and Deployment

### Step 1: Create Migration

Already created: `migrations/versions/b8c3d4e5f6a7_add_transaction_model.py`

### Step 2: Apply Migration

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Apply migration
flask db upgrade

# Verify
flask shell
>>> from models import Transaction
>>> Transaction.query.count()
0
```

### Step 3: Verify Relationships

```bash
flask shell
>>> from models import User, Booking, Transaction
>>> user = User.query.first()
>>> user.wallet_balance
Decimal('100.00')
>>> booking = Booking.query.first()
>>> booking.user
<User ...>
>>> transaction = Transaction.query.first()
>>> transaction.booking
<Booking ...>
```

---

## Testing Workflow

### Manual Testing Checklist

#### 1. Recharge Wallet
```
1. Login as regular user
2. Navigate to Dashboard
3. Click "Recharge" button on wallet card
4. Enter amount (e.g., 500)
5. Verify cost summary updates in real-time
6. Click "Recharge Now"
7. Verify:
   - Flash message shows success and new balance
   - Transaction appears in history
   - Navbar wallet balance updated
   - Dashboard wallet card updated
8. Repeat with edge cases:
   - Amount = 0.01 (minimum)
   - Amount = 100000 (maximum)
   - Amount = 100000.01 (exceeds limit, should fail)
```

#### 2. Booking with Payment
```
1. Login as regular user
2. Click "Stations" button
3. Click "Book" on any station
4. Enter booking duration (e.g., 60 minutes)
5. Verify cost summary:
   - Base rate: ₹0.50/min
   - Duration: 60 minutes
   - Estimated cost: ₹30.00
   - Balance after: correct calculation
6. Verify wallet balance sufficient
7. Click "Confirm Booking"
8. Verify:
   - Booking created successfully (flash message)
   - Wallet balance deducted (₹30.00 - check dashboard)
   - Transaction appears in history with type=booking
   - Station available_slots decremented
9. Test insufficient balance:
   - User with ₹10 balance
   - Try 60-minute booking (costs ₹30)
   - Should show insufficient balance error
   - Redirect to recharge page
   - After recharge, booking succeeds
```

#### 3. Transaction History
```
1. Login as user with transactions
2. Click wallet balance button (navbar)
3. Verify transaction history page:
   - Current balance card matches dashboard
   - All transactions display with correct details
   - Dates formatted correctly
   - Amounts show correct sign (negative=debit, positive=credit)
   - Status badges color correctly
   - Booking transactions show station name + duration
4. Filter by transaction type (inspect browser/database)
5. Verify balance_after column shows progression
```

#### 4. RBAC Integration
```
1. Login as admin user
2. Verify access to admin dashboard (not user dashboard)
3. Admin can recharge wallet (if needed)
4. Admin can view transactions
5. Booking payment logic applies to admins too
6. Logout and verify non-authenticated users:
   - Cannot access /payment/transactions
   - Cannot access /payment/recharge
   - Redirect to login
```

#### 5. Edge Cases
```
1. Recharge with invalid amount formats:
   - "abc" (non-numeric)
   - "-100" (negative)
   - "0.999" (rounds to precision)
2. Booking with exact balance:
   - User has ₹30.00
   - Book for 60 minutes (costs ₹30.00)
   - Should succeed with ₹0.00 balance
3. Concurrent bookings (if using load testing):
   - Two users booking last slot simultaneously
   - Only one should succeed (row lock protects)
   - Failed booking should not deduct wallet
4. Database failure simulation:
   - Booking creation succeeds, transaction fails
   - Rollback should undo wallet deduction
   - No orphaned bookings or transactions
```

### Automated Testing (Future)

```python
# tests/test_payment.py
def test_recharge_wallet():
    user = create_test_user()
    initial_balance = user.wallet_balance
    
    response = client.post('/payment/recharge', data={
        'amount': '100.00',
        'csrf_token': get_csrf_token(response)
    })
    
    assert response.status_code == 302
    user.refresh()  # Reload from DB
    assert user.wallet_balance == initial_balance + Decimal('100.00')

def test_insufficient_balance_blocks_booking():
    user = create_test_user(wallet_balance=Decimal('10.00'))
    station = create_test_station()
    
    response = client.post('/bookings', data={
        'station_id': station.id,
        'booking_time': future_datetime(),
        'charging_duration': '60',  # Costs ₹30
        'csrf_token': get_csrf_token(response)
    })
    
    assert response.status_code == 302
    assert response.location == url_for('payment.recharge')
    user.refresh()
    assert user.wallet_balance == Decimal('10.00')  # Unchanged
```

---

## Git Commit Message

```
feat(payment): implement wallet and payment simulation system

- Add Transaction model with complete audit trail
- Implement wallet recharge flow with form and validation
- Integrate payment deduction into booking creation
- Add transaction history page with dashboard display
- Update booking form with real-time cost calculator
- Add wallet balance display to navbar
- Use atomic database transactions for financial consistency
- Include pagination and query optimization (no N+1)
- Add comprehensive RBAC integration with payment routes
- Create responsive Bootstrap payment UI templates

Technical Details:
- Transaction model stores debits/credits with balance snapshots
- Booking creation wrapped in try/except with rollback
- Row-level locks prevent race conditions on stations
- Pricing configuration via BASE_RATE_PER_MINUTE constant
- All amounts stored as Decimal(10,2) for precision
- CSRF protection on all mutation endpoints
- Query optimizations with joinedload and aggregations

Breaking Changes: None
Backwards Compatible: Yes (wallet_balance already in User model)

Files Changed:
- models/transaction.py (new)
- migrations/versions/b8c3d4e5f6a7_add_transaction_model.py (new)
- routes/payment.py (new)
- routes/bookings.py (modified: add payment logic)
- routes/__init__.py (modified: register payment blueprint)
- utils/payment.py (new)
- models/__init__.py (modified: export Transaction)
- templates/payment/recharge.html (new)
- templates/payment/transactions.html (new)
- templates/bookings/new.html (modified: add cost calculator)
- templates/dashboard/user.html (modified: add wallet card)
- templates/base.html (modified: wallet link in navbar)
```

---

## Deployment Checklist

- [ ] Run migration: `flask db upgrade`
- [ ] Test recharge flow (manual)
- [ ] Test booking with payment deduction (manual)
- [ ] Verify transaction history displays correctly
- [ ] Check dashboard wallet card updates
- [ ] Verify RBAC integration (admin/user access)
- [ ] Load test for concurrency (if applicable)
- [ ] Monitor transaction logs for any failures
- [ ] Communicate pricing to users
- [ ] Create user documentation for recharge flow

---

## Future Enhancements

1. **Refund on Cancellation:** Add refund transaction type and logic
2. **Payment Gateway Integration:** Replace simulation with real Stripe/RazorPay
3. **Discounts/Coupons:** Add coupon codes that reduce booking cost
4. **Monthly Subscription:** Flat-rate monthly plans
5. **Admin Wallet Management:** Admins can manually adjust user balances (audit trail)
6. **Email Receipts:** Send transaction confirmation emails
7. **Wallet Limits:** Set minimum/maximum balance per user
8. **Transaction Filtering:** Filter by date range, transaction type in UI
9. **Export Statements:** CSV/PDF export of transaction history
10. **Analytics Dashboard:** Admin view of wallet revenue, booking frequency

---

## Troubleshooting

### Issue: "Your session has expired" on recharge
**Solution:** Clear browser cookies and retry. CSRF token must match session.

### Issue: Wallet balance not updating immediately
**Solution:** Browser caching. Hard refresh (Ctrl+Shift+R) or check server-side via `flask shell`

### Issue: Transaction created but booking not found
**Solution:** Booking was cancelled after transaction. Check booking status in database.

### Issue: Insufficient balance error even with ₹0 remaining
**Solution:** Precision issue. Verify: `user.wallet_balance >= booking_cost` (not `>`). Already handled in code.

### Issue: Admin can see user's transactions
**Solution:** By design. Transaction history is user-scoped (filter by current_user.id). Admins see only their own transactions.

---

## FAQ

**Q: Can bookings be cancelled to refund wallet?**
A: Not yet. Cancellations set status="cancelled" but don't refund. Refund logic is a future enhancement.

**Q: What if a booking is deleted from the database?**
A: Transaction record orphans but persists (booking_id set to NULL). Audit trail remains intact.

**Q: Can wallets go negative?**
A: No. Validator on User model prevents negative balance. Bookings deduct only if balance sufficient.

**Q: How are decimal amounts handled?**
A: All amounts are Decimal(10,2) for precision. No floating-point arithmetic used.

**Q: Is payment PCI-compliant?**
A: This is a simulation. Real payment gateways must handle PCI compliance separately.

---

## Support

For issues or questions:
1. Check this documentation
2. Review code comments in affected files
3. Examine database transactions table
4. Check application logs for errors
5. Run manual test workflow above
