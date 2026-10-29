# ShopEase E-Commerce Application

## Technology Stack
- Python
- Django
- Django REST Framework
- PostgreSQL
- HTML, CSS and Bootstrap

## Application Features
- Product catalogue and product detail pages
- Product variants and inventory management
- Shopping cart and quantity validation
- Coupons and discounts
- Checkout and order management
- Payment workflows
- Wishlist
- Product reviews
- User accounts and authentication
- Administration
- Notifications and analytics

## Project Setup

1. Install Python and PostgreSQL.
2. Open the backend directory in PowerShell.
3. Activate the project's virtual environment.
4. Install dependencies using requirements.txt.
5. Configure the environment variables in the project-root .env file.
6. Ensure the PostgreSQL database and credentials match the configuration.
7. Apply migrations.
8. Create an administrator account if required.
9. Start the development server.

## Common Commands

Run from the backend directory:

    python -m pip install -r requirements.txt
    python manage.py check
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py runserver

## Tests

Run the Django test suite with:

    python manage.py test --noinput

## Local URLs

- Storefront: http://127.0.0.1:8000/
- API health endpoint: http://127.0.0.1:8000/api/health/

## Environment and Security

The project-root .env file contains local configuration and secrets.
Never commit real credentials or secret keys to version control.

Before production deployment, configure DEBUG, SECRET_KEY, allowed hosts,
database credentials, HTTPS, secure cookies, static files, media storage,
logging and backups appropriately.

## Documentation Note

This README describes the project at a high level. Confirm configuration
values and available endpoints against the existing project before deployment.
