from django.db.models import Avg, Count, F
from django.shortcuts import get_object_or_404, render

from products.models import Product
from products.views import active_products
from reviews.models import Review


def home(request):
    products = active_products()[:12]

    return render(
        request,
        "storefront/home.html",
        {"products": products},
    )


def product_detail(request, product_id):
    product = get_object_or_404(
        active_products(),
        pk=product_id,
    )

    # Increment product views safely in the database.
    Product.objects.filter(pk=product.pk).update(
        view_count=F("view_count") + 1
    )
    product.view_count += 1

    # Get published and approved customer reviews.
    published_reviews = Review.objects.filter(
        product_id=product.pk,
        status=Review.Status.PUBLISHED,
        is_approved=True,
    )

    # Calculate the average rating and total number of reviews.
    review_summary = published_reviews.aggregate(
        average_rating=Avg("rating"),
        total_reviews=Count("id"),
    )

    average_rating = review_summary["average_rating"] or 0
    total_reviews = review_summary["total_reviews"]

    # Display the five most recent published reviews.
    reviews = (
        published_reviews
        .select_related("user")
        .prefetch_related("images")
        .order_by("-created_at", "-id")[:5]
    )

    # Find other active products in the same category.
    related_products = (
        active_products()
        .filter(category_id=product.category_id)
        .exclude(pk=product.pk)
        [:4]
    )

    context = {
        "product": product,
        "average_rating": average_rating,
        "total_reviews": total_reviews,
        "reviews": reviews,
        "related_products": related_products,
    }

    return render(
        request,
        "storefront/product_detail.html",
        context,
    )


def login_page(request):
    return render(request, "storefront/login.html")

def checkout_page(request):
    return render(request, "storefront/checkout.html")

def cart_page(request):
    return render(request, "storefront/cart.html")

def my_orders_page(request):
    return render(request, "storefront/my_orders.html")


def order_confirmation_page(request):
    return render(request, "storefront/order_confirmation.html")

def my_addresses_page(request):
    return render(request, "storefront/my_addresses.html")


def register_page(request):
    return render(request, "storefront/register.html")



def wishlist_page(request):
    return render(request, "storefront/wishlist.html")