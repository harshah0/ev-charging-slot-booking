# Database Seeding Guide

This project includes a safe, idempotent seed system for local development and controlled production provisioning.

## What it seeds
- 1 admin user
- 3 demo charging stations

## Default admin
- Email: `admin@ev.com`
- Password: `Admin123`

## Command

```bash
flask seed run
```

## Production safety
- The seed command is blocked in production by default.
- To run intentionally in production, set:

```bash
ALLOW_PRODUCTION_SEEDING=true
```

## Environment overrides
You can override the default admin credentials with environment variables:
- `SEED_ADMIN_USERNAME`
- `SEED_ADMIN_EMAIL`
- `SEED_ADMIN_PASSWORD`

## Idempotency behavior
- Existing admin user is reused by email.
- Existing charging stations are reused by station name.
- Re-running the command does not create duplicates.
- Station details are updated to match the seed definitions.

## Why production databases start empty
Production databases are usually provisioned as blank managed instances. They do not carry over local development rows because:
- local SQLite is a different database engine and file
- production uses a separate PostgreSQL instance
- deployments should not automatically copy developer data

## Why local SQLite data does not exist on Render PostgreSQL
Your local SQLite file lives on your machine. Render provisions a separate PostgreSQL database in its own environment, so local rows are not present unless you seed or migrate them explicitly.

## How seed systems are used in SaaS apps
Seed systems are used to provision predictable bootstrap data such as:
- admin accounts
- demo tenants
- lookup tables
- sample catalog items

They help teams bring up a brand-new environment quickly without manually inserting rows.
