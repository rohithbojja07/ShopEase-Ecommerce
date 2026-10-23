from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Address
from cart.models import Cart, CartItem
from orders.models import Order
from orders.services import place_order, set_status
from payments.services import create_payment, verify_payment
from products.models import ProductVariant


class Command(BaseCommand):
    help = "Create a delivered demo order for a user (for trying out returns)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError("No user with that email.")
        address = Address.objects.filter(
            user=user, address_type=Address.AddressType.SHIPPING
        ).first()
        if address is None:
            address = Address.objects.create(
                user=user, address_type=Address.AddressType.SHIPPING,
                full_name=user.first_name or "Demo Customer", phone="9876543210",
                line1="12 Main Road", city="Hyderabad", state="Telangana",
                postal_code="500001",
            )
        variants = list(
            ProductVariant.objects.filter(is_active=True, inventory__available_stock__gte=3)
            .order_by("sku")[:2]
        )
        if len(variants) < 2:
            raise CommandError("Not enough stocked variants. Run seed_inventory first.")

        cart, _ = Cart.objects.get_or_create(user=user)
        cart.items.all().delete()
        CartItem.objects.create(cart=cart, variant=variants[0], quantity=2)
        CartItem.objects.create(cart=cart, variant=variants[1], quantity=1)

        order = place_order(user, address.id)
        payment, _ = create_payment(user, order.id, "CARD")
        verify_payment(user, payment.id, payment.transaction_reference, "tok_success")
        order = Order.objects.get(pk=order.pk)
        for step in ("PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"):
            set_status(order, step)
        self.stdout.write(self.style.SUCCESS(
            f"Delivered order {order.order_number} (id {order.id}) is ready for return testing."
        ))
