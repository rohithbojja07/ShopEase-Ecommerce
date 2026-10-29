# ShopEase Deployment Guide

## 1. Prerequisites

- Python and the dependencies in `requirements.txt`
- A configured PostgreSQL database
- A production server and domain name
- HTTPS configured for the production domain

## 2. Environment Configuration

Configure the project-root `.env` file with the production environment values.

Required settings include:

- `SECRET_KEY`: a unique, securely generated secret
- `DEBUG`: set to `False` in production
- `DB_NAME`: production database name
- `DB_USER`: production database user
- `DB_PASSWORD`: production database password
- `DB_HOST`: production database host
- `DB_PORT`: database port

Never commit `.env` or expose production credentials.

## 3. Django Security

Before deployment:

- Configure `ALLOWED_HOSTS` for the actual production domain.
- Configure HTTPS and secure session and CSRF cookies.
- Configure `SECURE_SSL_REDIRECT` only when HTTPS is correctly available.
- Configure HSTS after confirming HTTPS works throughout the deployment.
- Keep `DEBUG=False`.
- Review the output of `python manage.py check --deploy`.

Do not enable production-only settings blindly in local HTTP development.

## 4. Database

- Create the production database and user.
- Apply migrations with `python manage.py migrate`.
- Establish a regular backup and restore procedure.
- Restrict database access to trusted hosts and users.

## 5. Static and Media Files

- Configure `STATIC_ROOT` and collect static files using `python manage.py collectstatic`.
- Configure persistent media storage for uploaded product images and other user uploads.
- Do not assume user-uploaded media is included in application deployments.

## 6. Dependencies and Startup

Install dependencies:

    python -m pip install -r requirements.txt

Run Django's deployment checks:

    python manage.py check --deploy

Use a suitable production application server and follow its deployment instructions. Do not use Django's development server as the production server.

## 7. Operational Readiness

Before releasing:

- Configure application logging and error monitoring.
- Confirm database backups and recovery procedures.
- Protect administrative accounts and credentials.
- Review payment-provider settings and webhook security.
- Confirm domain, HTTPS, static files, and media storage.

## Important

This guide documents deployment preparation. Actual production readiness depends on
the hosting environment, Django settings, database configuration, and infrastructure.
