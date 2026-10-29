# ShopEase Database Setup

## Database Engine
ShopEase is configured to use PostgreSQL through Django.

## Environment Variables
The backend reads its environment variables from the project-root `.env` file.

Required database variables:

- `DB_NAME`: PostgreSQL database name
- `DB_USER`: PostgreSQL database username
- `DB_PASSWORD`: PostgreSQL database password
- `DB_HOST`: Database host; defaults to `localhost`
- `DB_PORT`: Database port; defaults to `5432`

The database credentials must match an existing PostgreSQL database and user.

## Initial Setup

1. Install and start PostgreSQL.
2. Create the database and configure a database user.
3. Configure the database variables in the project-root `.env` file.
4. From the backend directory, apply Django migrations:

   `python manage.py migrate`

5. To create an administrator account, run:

   `python manage.py createsuperuser`

## Database Configuration
The Django database engine is `django.db.backends.postgresql`.

Do not commit `.env` or disclose database passwords. Keep `.env.example` limited to placeholder values.

## Notes
This document describes the configuration found in the Django settings.
The actual database name, credentials, connection status, backups, and production
database configuration must be verified separately.
