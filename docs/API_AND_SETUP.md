# ShopEase API and Application Setup

## 1. Storefront Pages

The following page routes are registered in `core/storefront_urls.py`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Storefront home |
| GET | `/login/` | Login page |
| GET | `/register/` | Registration page |
| GET | `/products/<product_id>/` | Product details |
| GET | `/cart/` | Shopping cart page |
| GET | `/checkout/` | Checkout page |
| GET | `/my-orders/` | Customer orders |
| GET | `/my-addresses/` | Customer addresses |
| GET | `/order-confirmation/` | Order confirmation page |

These paths are registered by Django. Verify supported HTTP methods and authentication requirements in the corresponding views.

## 2. Authentication and Utility Routes

Registered in `config/urls.py`:

| Path | Purpose |
|---|---|
| `/forgot-password/` | Forgot-password page |
| `/api/health/` | Health endpoint |
| `/api/auth/login/` | JWT login endpoint |
| `/api/auth/token/refresh/` | JWT token refresh endpoint |
| `/admin/` | Django administration |
| `/admin/password_reset/` | Admin password-reset initiation |
| `/reset/<uidb64>/<token>/` | Password-reset confirmation |
| `/reset/done/` | Password-reset completion |

The login endpoint uses Simple JWT's `TokenObtainPairView`; the refresh endpoint uses `TokenRefreshView`.

## 3. API Route Groups

The root URL configuration includes these application URL modules:

| Prefix | Application |
|---|---|
| `/api/admin/analytics/` | Analytics |
| `/api/admin/` | Staff API and review staff routes |
| `/api/` | Accounts |
| `/api/` | Products |
| `/api/` | Cart |
| `/api/` | Orders |
| `/api/` | Payments |
| `/api/` | Notifications |
| `/api/` | Reviews |

The precise endpoint paths, HTTP methods, request formats, response formats, and permission requirements are defined in each application's URL configuration, views, and serializers. Consult those files before integrating a client.

## 4. Local Development Setup

From the backend directory:

1. Activate the existing Python virtual environment.
2. Install dependencies from `requirements.txt`.
3. Configure the project-root `.env` file.
4. Ensure PostgreSQL is configured using the database setup guide.
5. Apply migrations.
6. Start the Django development server.

Commands:

    python -m pip install -r requirements.txt
    python manage.py migrate
    python manage.py runserver

The local storefront is normally available at `http://127.0.0.1:8000/`.

## 5. Authentication Notes

The API registers JWT login and token-refresh routes. Review each protected endpoint's permission classes before use. Do not share access tokens or credentials.

## 6. Media

When `DEBUG` is enabled, Django serves configured media files through the development URL configuration. Production media serving must be configured separately.

## 7. Related Documentation

- `DATABASE_SETUP.md` — PostgreSQL configuration
- `DEPLOYMENT.md` — production deployment preparation
- `../backend/README.md` — project overview and setup

## Documentation Scope

This document describes route registrations visible in the root URL configuration. It is not a complete endpoint specification for every included application.
