from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command

from orders.models import Order
from orders.services import place_order
from orders.tests import fill_cart, make_address
from payments.services import create_payment, verify_payment

PASSWORD = "Str0ng!Pass#2026"
User = get_user_model()


def setup_roles():
    call_command("setup_roles", stdout=StringIO())


def make_staff(email, role, password=PASSWORD):
    call_command("create_staff", email, role=role, password=password, stdout=StringIO())
    return User.objects.get(email=email)


def role_permissions(name):
    group = Group.objects.get(name=name)
    return {
        f"{p.content_type.app_label}.{p.codename}"
        for p in group.permissions.select_related("content_type")
    }


def placed_order(user, variant, quantity=1):
    """An order that is placed but not paid."""
    address = user.addresses.filter(address_type="SHIPPING").first() or make_address(user)
    fill_cart(user, variant, quantity)
    return place_order(user, address.id)


def paid_order(user, variant, quantity=1):
    """A paid order (status CONFIRMED)."""
    order = placed_order(user, variant, quantity)
    payment, _ = create_payment(user, order.id, "CARD")
    verify_payment(user, payment.id, payment.transaction_reference, "tok_success")
    return Order.objects.get(pk=order.pk)
