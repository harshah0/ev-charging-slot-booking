# Database Migration Guide

This guide explains how to manage database schema changes using Flask-Migrate (Alembic).

---

## Quick Start

### Prerequisites
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Verify Flask-Migrate is installed
pip list | grep Flask-Migrate
# Output: Flask-Migrate    4.1.0
```

### Current Migrations

**1. Add role column to users table** (RBAC)
- **File:** `migrations/versions/a7b2c4d5e6f7_add_role_column_to_users.py`
- **Adds:** `role` VARCHAR(20) column to users table with default='user'
- **Indexes:** Index on role for efficient role-based queries

**2. Add transaction model** (Payment/Wallet)
- **File:** `migrations/versions/b8c3d4e5f6a7_add_transaction_model.py`
- **Adds:** `transactions` table with all columns, relationships, and indexes
- **Indexes:** user_id, booking_id, transaction_type, status, created_at

---

## Common Commands

### Apply All Pending Migrations

```bash
flask db upgrade
```

**Output:**
```
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume sqlite database.
INFO  [alembic.runtime.migration] Running upgrade  -> a7b2c4d5e6f7, add role column to users
INFO  [alembic.runtime.migration] Running upgrade a7b2c4d5e6f7 -> b8c3d4e5f6a7, add transaction model
```

**What It Does:**
- Reads migration files from `migrations/versions/`
- Applies migrations in order (determined by file timestamp)
- Updates `alembic_version` table to track applied migrations
- Idempotent: running twice has no effect (already applied migrations skipped)

---

### Apply Specific Revision

```bash
# Apply up to a specific revision
flask db upgrade b8c3d4e5f6a7

# Jump back one revision
flask db downgrade -1

# Jump back to specific revision
flask db downgrade a7b2c4d5e6f7
```

---

### Check Current Schema Version

```bash
flask shell

>>> from extensions import db
>>> from sqlalchemy import inspect
>>> inspector = inspect(db.engine)
>>> inspector.get_table_names()
['users', 'charging_stations', 'bookings', 'transactions']
>>> inspector.get_columns('transactions')
[
    {'name': 'id', 'type': INTEGER(), ...},
    {'name': 'user_id', 'type': INTEGER(), ...},
    {'name': 'booking_id', 'type': INTEGER(), ...},
    ...
]
```

---

### Create New Migration (After Model Changes)

```bash
# 1. Modify model file (e.g., models/user.py)
#    Add new field to User class

# 2. Create migration
flask db migrate -m "add_email_verified_to_users"

# Output: Created migration: migrations/versions/c9d4e5f6a7b8_add_email_verified_to_users.py

# 3. Review generated migration
cat migrations/versions/c9d4e5f6a7b8_add_email_verified_to_users.py
# Verify up() and down() functions are correct

# 4. Apply migration
flask db upgrade

# 5. Test the change
flask shell
>>> from models import User
>>> from extensions import db
>>> from sqlalchemy import inspect
>>> inspector = inspect(db.engine)
>>> [col['name'] for col in inspector.get_columns('users')]
['id', 'username', 'password', 'role', 'wallet_balance', 'email_verified', ...]
```

---

## Migration Details

### RBAC Migration: Add Role Column

**File:** `migrations/versions/a7b2c4d5e6f7_add_role_column_to_users.py`

**Schema Change:**
```sql
ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user';
CREATE INDEX ix_users_role ON users (role);
```

**Reverse (Downgrade):**
```sql
DROP INDEX ix_users_role;
ALTER TABLE users DROP COLUMN role;
```

**Why Needed:**
- Enables role-based access control (admin vs user)
- Indexed for efficient dashboard queries filtering by role

**Validation:**
```bash
flask shell
>>> from models import User
>>> user = User.query.first()
>>> user.role
'user'
>>> user.is_admin()
False
```

---

### Payment Migration: Add Transaction Model

**File:** `migrations/versions/b8c3d4e5f6a7_add_transaction_model.py`

**Schema Created:**
```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    booking_id INTEGER,
    transaction_type VARCHAR(20) NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    description TEXT,
    balance_after NUMERIC(10,2),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
    CHECK (amount != 0)
);

-- Indexes for performance
CREATE INDEX ix_transactions_booking_id ON transactions(booking_id);
CREATE INDEX ix_transactions_user_id ON transactions(user_id);
CREATE INDEX ix_transactions_transaction_type ON transactions(transaction_type);
CREATE INDEX ix_transactions_status ON transactions(status);
CREATE INDEX ix_transactions_created_at ON transactions(created_at);
```

**Relationships:**
- `transactions.user_id` → `users.id` (ON DELETE CASCADE: delete transactions if user deleted)
- `transactions.booking_id` → `bookings.id` (ON DELETE SET NULL: keep transactions if booking deleted)

**Validation:**
```bash
flask shell
>>> from models import Transaction, User, Booking
>>> Transaction.query.count()
0
>>> t = Transaction.query.first()
>>> None
>>> # Create a test transaction
>>> from models import Transaction, TransactionStatus, TransactionType
>>> from decimal import Decimal
>>> user = User.query.first()
>>> txn = Transaction(
...     user_id=user.id,
...     transaction_type=TransactionType.RECHARGE.value,
...     amount=Decimal('100.00'),
...     status=TransactionStatus.COMPLETED.value,
...     description='Test recharge',
...     balance_after=Decimal('500.00')
... )
>>> from extensions import db
>>> db.session.add(txn)
>>> db.session.commit()
>>> Transaction.query.count()
1
```

---

## Production Deployment

### Pre-Deployment Checklist

```bash
# 1. Backup database
cp ev_charging.db ev_charging.backup.db

# 2. Test migrations on development
flask db upgrade

# 3. Run test suite
pytest

# 4. Verify schema
flask shell
>>> from extensions import db
>>> from sqlalchemy import inspect
>>> inspector = inspect(db.engine)
>>> sorted([t for t in inspector.get_table_names()])
['bookings', 'charging_stations', 'transactions', 'users']
```

### Deployment Steps

```bash
# 1. Pull latest code
git pull origin main

# 2. Activate virtual environment
source venv/bin/activate

# 3. Install dependencies (if any new migrations added)
pip install -r requirements.txt

# 4. Apply migrations
flask db upgrade

# 5. Restart application
# (depends on your deployment method)
systemctl restart ev-charging-service
# OR
pkill -f "gunicorn.*app:app"
gunicorn app:app

# 6. Verify
curl http://localhost:5000/health
# Should return 200 OK
```

### Rollback in Production (Emergency)

```bash
# If migration causes issues:

# 1. Identify current version
flask db current
# Output: b8c3d4e5f6a7

# 2. Downgrade to previous version
flask db downgrade -1
# Output: Downgrade to a7b2c4d5e6f7

# 3. Restart application
systemctl restart ev-charging-service

# 4. Investigate the issue
# - Check migration file for errors
# - Review application logs
# - Fix and re-test locally

# 5. Re-apply after fix
flask db upgrade
```

---

## Troubleshooting

### Issue: "Target database is not up to date"

```bash
# Reason: Pending migrations haven't been applied

# Solution:
flask db upgrade

# Verify:
flask db current
```

### Issue: "alembic_version table not found"

```bash
# Reason: First time running migrations

# Solution:
flask db upgrade

# This creates alembic_version table and applies all migrations
```

### Issue: "Duplicate constraint violation"

```bash
# Reason: Migration run twice (idempotency issue)

# Check migration status:
flask db history

# If migration already applied, skip it:
flask db stamp b8c3d4e5f6a7

# Re-apply:
flask db upgrade
```

### Issue: "Cannot add NOT NULL column without default"

```bash
# Reason: Some databases (older SQLite) don't support this

# Solution in migration file:
# Add `server_default` parameter:
op.add_column('users', sa.Column('role', sa.String(20), 
                                   server_default='user',  # Add this
                                   nullable=False))
```

### Issue: "Foreign key constraint violation"

```bash
# Reason: Deleting record with active children

# Solution: Migrations handle this with ON DELETE CASCADE/SET NULL
# Check:
flask shell
>>> from sqlalchemy import inspect, ForeignKeyConstraint
>>> inspector = inspect(db.engine)
>>> fks = inspector.get_foreign_keys('transactions')
>>> fks[0]
{'name': 'fk_transactions_user_id_users_id',
 'constrained_columns': ['user_id'],
 'referred_schema': None,
 'referred_table': 'users',
 'referred_columns': ['id'],
 'options': {'ondelete': 'CASCADE'}}
```

---

## Migration Best Practices

### Do's ✅

1. **Always test migrations on a copy of production data**
   ```bash
   cp production.db test_migration.db
   export DATABASE_URL="sqlite:///test_migration.db"
   flask db upgrade
   ```

2. **Review generated migrations before applying**
   ```bash
   # Compare with model changes
   git diff models/
   cat migrations/versions/<latest>_*.py
   ```

3. **Keep migrations focused (one change per migration)**
   - ❌ Bad: "refactor database schema"
   - ✅ Good: "add email_verified column to users"

4. **Test downgrade/upgrade cycle**
   ```bash
   flask db downgrade -1
   flask db upgrade
   ```

5. **Document complex migrations**
   ```python
   def upgrade():
       """
       Add email verification tracking.
       
       This allows tracking which users have verified their email address.
       Existing users default to unverified (safe default).
       """
   ```

### Don'ts ❌

1. **Don't modify migration files after applying them**
   - Migration files are immutable records
   - If errors found, create a NEW migration to fix

2. **Don't use `migrate` on production without testing**
   ```bash
   # ❌ Risky
   flask db migrate && flask db upgrade  # On production!
   
   # ✅ Safe
   flask db migrate  # On development
   # Review migration file
   # Test on staging
   # Deploy to production
   ```

3. **Don't mix multiple schema changes in one migration**
   - Harder to debug if one part fails
   - Harder to review

4. **Don't delete migration files**
   - Migration history is immutable
   - If you need to undo, create downgrade migration

---

## Advanced Usage

### Check Migration Status

```bash
flask db history
# Output:
# <base> -> a7b2c4d5e6f7 (head), add role column to users
# <base> -> b8c3d4e5f6a7 (head), add transaction model

flask db branches
# Output:
# * a7b2c4d5e6f7@main
```

### Merge Migration Branches (Multi-Developer)

```bash
# If two developers created migrations independently:
# a7b2c4d5e6f7_add_role_column_to_users.py (developer 1)
# c9d4e5f6a7b8_add_email_verification.py (developer 2)

# Resolve by creating merge commit:
flask db merge a7b2c4d5e6f7 c9d4e5f6a7b8 --message "merge schema changes"

# This creates a new migration that depends on both parents
```

### Export Schema to SQL

```bash
# Generate SQL without executing
flask db upgrade --sql

# Output:
# BEGIN;
# ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user';
# CREATE INDEX ix_users_role ON users(role);
# ...
# COMMIT;
```

### Validate Schema Against Models

```bash
# Check if models match database schema
flask shell
>>> from alembic.config import Config
>>> from alembic.script import ScriptDirectory
>>> from alembic.runtime.migration import MigrationContext
>>> from alembic.operations import Operations
>>> from extensions import db
>>> from alembic.ext.declarative import declarative_base

# (More complex - usually not needed in development)
# Use this to audit before production deployment
```

---

## Production Ready Checklist

- [ ] All migrations applied: `flask db current` shows latest version
- [ ] No pending migrations: `flask db upgrade` runs with no changes
- [ ] Schema validated: `flask shell` can import all models
- [ ] Downgrade tested: `flask db downgrade -1` followed by `flask db upgrade` succeeds
- [ ] Performance verified: Large tables have necessary indexes
- [ ] Backup created: Database backed up before migration
- [ ] Monitoring enabled: Application logs checked post-migration
- [ ] Rollback plan documented: Team knows how to revert if issues arise

---

## Reference

### Useful Commands

```bash
flask db init                           # Initialize migrations (one-time)
flask db migrate -m "message"           # Create new migration
flask db upgrade                        # Apply all pending migrations
flask db downgrade                      # Undo last migration
flask db current                        # Show current version
flask db history                        # Show all migrations
flask db branches                       # Show migration branches
flask db stamp <revision>               # Mark as applied without running
flask db merge <revision1> <revision2>  # Merge divergent migrations
```

### Documentation Links

- [Flask-Migrate Docs](https://flask-migrate.readthedocs.io/)
- [Alembic Docs](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Migrations Guide](https://docs.sqlalchemy.org/en/20/faq/migration_guide.html)

---

## Support

For migration issues:
1. Check this guide
2. Review migration file comments
3. Check Flask-Migrate and Alembic documentation
4. Examine application logs
5. Restore from backup if needed and re-test locally
