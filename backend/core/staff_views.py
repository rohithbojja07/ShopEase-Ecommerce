from django.apps import apps
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from core.roles import ROLES


def _require_staff(request):
    user = request.user

    if not (
        user.is_authenticated
        and user.is_active
        and user.is_staff
    ):
        raise PermissionDenied

    if user.is_superuser:
        return

    if not user.groups.filter(name__in=ROLES).exists():
        raise PermissionDenied


def _staff_role(user):
    if user.is_superuser:
        return "Super Admin"

    return user.groups.filter(name__in=ROLES).values_list(
        "name", flat=True
    ).first() or "Unassigned"


def _count_model(app_label, model_name):
    try:
        model = apps.get_model(app_label, model_name)
        return model.objects.count()
    except (LookupError, AttributeError):
        return None


def _dashboard_cards(user):
    definitions = [
        {
            "title": "Products",
            "app": "products",
            "model": "Product",
            "permission": "products.view_product",
        },
        {
            "title": "Orders",
            "app": "orders",
            "model": "Order",
            "permission": "orders.view_order",
        },
        {
            "title": "Customers",
            "app": "accounts",
            "model": "User",
            "permission": "accounts.view_user",
        },
        {
            "title": "Inventory Records",
            "app": "inventory",
            "model": "Inventory",
            "permission": "inventory.view_inventory",
        },
        {
            "title": "Returns",
            "app": "orders",
            "model": "ReturnRequest",
            "permission": "orders.view_returnrequest",
        },
    ]

    cards = []

    for item in definitions:
        if not user.is_superuser and not user.has_perm(item["permission"]):
            continue

        count = _count_model(item["app"], item["model"])

        if count is not None:
            cards.append({
                "title": item["title"],
                "count": count,
            })

    return cards


def _render_staff(request, template, context=None):
    _require_staff(request)

    data = {
        "staff_user": request.user,
        "staff_role": _staff_role(request.user),
    }

    if context:
        data.update(context)

    return render(request, template, data)


@require_http_methods(["GET", "POST"])
def staff_login(request):
    if request.user.is_authenticated:
        if request.user.is_staff and request.user.is_active:
            return redirect("staff_portal:dashboard")

    error = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=email,
            password=password,
        )

        if user is None:
            User = get_user_model()

            try:
                account = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                account = None

            if account is not None:
                user = authenticate(
                    request,
                    username=account.get_username(),
                    password=password,
                )

        if user is None:
            error = "Invalid email or password."
        elif not user.is_active:
            error = "This account is inactive."
        elif not user.is_staff:
            error = "You do not have access to the staff portal."
        elif not (
            user.is_superuser
            or user.groups.filter(name__in=ROLES).exists()
        ):
            error = "No staff role is assigned to this account."
        else:
            login(request, user)
            return redirect("staff_portal:dashboard")

    return render(
        request,
        "staff/login.html",
        {"error": error},
    )


@login_required(login_url="staff_portal:login")
def dashboard(request):
    return _render_staff(
        request,
        "staff/dashboard.html",
        {
            "cards": _dashboard_cards(request.user),
        },
    )


@login_required(login_url="staff_portal:login")
def products_page(request):
    _require_staff(request)

    if not (
        request.user.is_superuser
        or request.user.has_perm("products.view_product")
    ):
        raise PermissionDenied

    return _render_staff(
        request,
        "staff/products.html",
        {
            "page_title": "Product Management",
            "description": (
                "Manage the product catalogue using the existing "
                "staff API and permission rules."
            ),
            "endpoint": "/api/admin/products/",
            "can_add": (
                request.user.is_superuser
                or request.user.has_perm("products.add_product")
            ),
            "can_change": (
                request.user.is_superuser
                or request.user.has_perm("products.change_product")
            ),
        },
    )


@login_required(login_url="staff_portal:login")
def inventory_page(request):
    _require_staff(request)

    if not (
        request.user.is_superuser
        or request.user.has_perm("inventory.view_inventory")
    ):
        raise PermissionDenied

    return _render_staff(
        request,
        "staff/inventory.html",
        {
            "page_title": "Inventory Management",
            "description": (
                "Review inventory records. Stock changes must use "
                "the existing inventory validation and business rules."
            ),
            "endpoint": "/api/admin/inventory/",
            "can_add": (
                request.user.is_superuser
                or request.user.has_perm("inventory.add_inventory")
            ),
            "can_change": (
                request.user.is_superuser
                or request.user.has_perm("inventory.change_inventory")
            ),
        },
    )


@login_required(login_url="staff_portal:login")
def orders_page(request):
    _require_staff(request)

    if not (
        request.user.is_superuser
        or request.user.has_perm("orders.view_order")
    ):
        raise PermissionDenied

    return _render_staff(
        request,
        "staff/orders.html",
        {
            "can_change": (
                request.user.is_superuser
                or request.user.has_perm("orders.change_order")
            ),
        },
    )


@login_required(login_url="staff_portal:login")
def customers_page(request):
    _require_staff(request)

    if not (
        request.user.is_superuser
        or request.user.has_perm("accounts.view_user")
    ):
        raise PermissionDenied

    return _render_staff(
        request,
        "staff/customers.html",
        {
            "can_change": (
                request.user.is_superuser
                or request.user.has_perm("accounts.change_user")
            ),
        },
    )

@login_required(login_url="staff_portal:login")
def returns_page(request):
    _require_staff(request)

    can_view = (
        request.user.is_superuser
        or request.user.has_perm("orders.view_returnrequest")
    )

    if not can_view:
        raise PermissionDenied

    return _render_staff(
        request,
        "staff/returns.html",
        {
            "can_change": (
                request.user.is_superuser
                or request.user.has_perm("orders.change_returnrequest")
            ),
        },
    )


def audit_logs_page(request):
    _require_staff(request)

    if not (
        request.user.is_superuser
        or request.user.has_perm("core.view_auditlog")
    ):
        raise PermissionDenied

    return _render_staff(
        request,
        "staff/audit_logs.html",
        {
            "page_title": "Audit Logs",
            "description": (
                "Review recorded staff and system activity. "
                "Audit records are read-only."
            ),
            "endpoint": "/api/admin/audit-logs/",
            "can_add": False,
            "can_change": False,
        },
    )
@require_POST
def staff_logout(request):
    logout(request)
    return redirect("staff_portal:login")






