import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from core.shop_helpers import PASSWORD, make_staff
from orders.models import Order
from orders.test_returns import delivered_order, png
from orders.tests import make_variant

from .models import Review

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ReviewTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        call_command("setup_roles", stdout=StringIO())
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD, first_name="Alice", last_name="Smith")
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD)
        self.carol = User.objects.create_user(email="carol@example.com", password=PASSWORD)
        self.phone_v = make_variant("Review Phone", "1000.00", 20, "10")
        self.phone = self.phone_v.product
        self.cable_v = make_variant("Review Cable", "200.00", 20)
        self.alice_order = delivered_order(self.alice, [(self.phone_v, 1)])
        self.client.force_authenticate(self.alice)

    def body(self, **extra):
        data = {"product_id": self.phone.id, "rating": 5, "title": "Great phone", "body": "Loved it"}
        data.update(extra)
        return data

    def post_review(self, **extra):
        return self.client.post("/api/reviews/", self.body(**extra), format="json")

    def reviews_url(self):
        return f"/api/products/{self.phone.id}/reviews/"

    def bob_buys(self):
        delivered_order(self.bob, [(self.phone_v, 1)])


class ReviewCreationTests(ReviewTestCase):
    def test_eligibility(self):
        ok = self.client.get(f"/api/reviews/eligibility/?product_id={self.phone.id}")
        self.assertTrue(ok.data["can_review"])
        never_bought = self.client.get(f"/api/reviews/eligibility/?product_id={self.cable_v.product_id}")
        self.assertFalse(never_bought.data["can_review"])

    def test_a_purchaser_can_review_and_it_is_marked_verified(self):
        response = self.post_review()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["rating"], 5)
        self.assertTrue(response.data["verified_purchase"])
        self.assertEqual(response.data["status"], "PUBLISHED")
        self.assertEqual(response.data["reviewer"], "Alice S.")
        self.assertNotIn("alice@example.com", str(response.data))

    def test_cannot_review_a_product_you_did_not_buy(self):
        response = self.post_review(product_id=self.cable_v.product_id)
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.post_review().status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_cannot_review_before_delivery(self):
        Order.objects.filter(pk=self.alice_order.pk).update(status="SHIPPED")
        self.assertEqual(self.post_review().status_code, 400)

    def test_only_one_review_per_product(self):
        self.assertEqual(self.post_review().status_code, 201)
        self.assertEqual(self.post_review(rating=1).status_code, 400)
        self.assertEqual(Review.objects.count(), 1)

    def test_input_validation(self):
        self.assertEqual(self.post_review(rating=6).status_code, 400)
        self.assertEqual(self.post_review(rating=0).status_code, 400)
        no_title = self.client.post("/api/reviews/", {"product_id": self.phone.id, "rating": 4}, format="json")
        self.assertEqual(no_title.status_code, 400)
        self.assertEqual(self.client.post("/api/reviews/", self.body(product_id=999999), format="json").status_code, 404)

    def test_reviews_require_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.post_review().status_code, 401)

    def test_images_at_creation_and_afterwards(self):
        data = {"product_id": self.phone.id, "rating": 4, "title": "With photos", "images": [png("a.png"), png("b.png")]}
        created = self.client.post("/api/reviews/", data, format="multipart")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(len(created.data["images"]), 2)
        url = f"/api/reviews/{created.data['id']}/images/"
        more = self.client.post(url, {"images": [png("c.png"), png("d.png"), png("e.png")]}, format="multipart")
        self.assertEqual(more.status_code, 201, more.data)
        self.assertEqual(len(more.data["images"]), 5)
        self.assertEqual(self.client.post(url, {"images": [png("f.png")]}, format="multipart").status_code, 400)

    def test_fake_images_are_rejected(self):
        review = self.post_review().data
        fake = SimpleUploadedFile("proof.png", b"not an image", content_type="image/png")
        response = self.client.post(f"/api/reviews/{review['id']}/images/", {"images": [fake]}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_edit_and_delete_your_own_review_only(self):
        review = self.post_review().data
        url = f"/api/reviews/{review['id']}/"
        edited = self.client.patch(url, {"rating": 3, "title": "Okay"}, format="json")
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual((edited.data["rating"], edited.data["title"]), (3, "Okay"))
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.patch(url, {"rating": 1}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.post_review().status_code, 201)  # can review again after deleting

    def test_my_reviews_list_is_private(self):
        self.post_review()
        self.assertEqual(self.client.get("/api/reviews/").data["count"], 1)
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/api/reviews/").data["count"], 0)


class ReviewDisplayTests(ReviewTestCase):
    def two_reviews(self):
        self.post_review(rating=5, title="Five stars")
        self.bob_buys()
        self.client.force_authenticate(self.bob)
        self.post_review(rating=3, title="Three stars")

    def test_summary_has_average_and_distribution(self):
        self.two_reviews()
        data = APIClient().get(self.reviews_url()).data
        self.assertEqual(data["summary"]["average"], 4.0)
        self.assertEqual(data["summary"]["count"], 2)
        self.assertEqual(data["summary"]["distribution"], {"5": 1, "4": 0, "3": 1, "2": 0, "1": 0})
        self.assertEqual(data["count"], 2)

    def test_the_public_list_never_shows_emails(self):
        self.two_reviews()
        response = APIClient().get(self.reviews_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("@example.com", str(response.data))

    def test_empty_product_has_an_empty_summary(self):
        data = APIClient().get(self.reviews_url()).data
        self.assertIsNone(data["summary"]["average"])
        self.assertEqual(data["summary"]["count"], 0)

    def test_filter_by_rating(self):
        self.two_reviews()
        data = APIClient().get(self.reviews_url() + "?rating=5").data
        self.assertEqual([r["title"] for r in data["results"]], ["Five stars"])

    def test_votes(self):
        self.post_review()
        review_id = Review.objects.get().id
        vote = f"/api/reviews/{review_id}/vote/"
        self.assertEqual(self.client.post(vote, {"helpful": True}, format="json").status_code, 400)  # own review
        self.client.force_authenticate(self.bob)
        first = self.client.post(vote, {"helpful": True}, format="json")
        self.assertEqual((first.data["helpful_count"], first.data["not_helpful_count"]), (1, 0))
        self.assertIs(first.data["my_vote"], True)
        changed = self.client.post(vote, {"helpful": False}, format="json")
        self.assertEqual((changed.data["helpful_count"], changed.data["not_helpful_count"]), (0, 1))
        removed = self.client.delete(vote)
        self.assertEqual((removed.data["helpful_count"], removed.data["not_helpful_count"]), (0, 0))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(vote, {"helpful": True}, format="json").status_code, 401)

    def test_ordering_by_helpful_votes(self):
        self.two_reviews()
        bobs = Review.objects.get(user=self.bob)
        self.client.force_authenticate(self.carol)
        self.client.post(f"/api/reviews/{bobs.id}/vote/", {"helpful": True}, format="json")
        data = self.client.get(self.reviews_url() + "?ordering=-helpful_count").data
        self.assertEqual(data["results"][0]["title"], "Three stars")
        self.assertIs(data["results"][0]["my_vote"], True)

    def test_product_list_shows_ratings_and_can_filter_and_sort(self):
        self.two_reviews()
        public = APIClient()
        rows = {r["name"]: r for r in public.get("/api/products/").data["results"]}
        self.assertEqual(rows["Review Phone"]["average_rating"], 4.0)
        self.assertEqual(rows["Review Phone"]["review_count"], 2)
        self.assertIsNone(rows["Review Cable"]["average_rating"])
        self.assertEqual(rows["Review Cable"]["review_count"], 0)
        names = [r["name"] for r in public.get("/api/products/?min_rating=4").data["results"]]
        self.assertEqual(names, ["Review Phone"])
        first = public.get("/api/products/?ordering=-average_rating").data["results"][0]
        self.assertEqual(first["name"], "Review Phone")


class ReviewModerationTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.cs = make_staff("support@example.com", "Customer Support")
        self.pm = make_staff("pm@example.com", "Product Manager")
        self.review_id = self.post_review().data["id"]

    def moderate(self, user, action, **body):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/admin/reviews/{self.review_id}/{action}/", body, format="json")

    def test_hiding_removes_the_review_from_the_public_list_and_average(self):
        self.assertEqual(self.moderate(self.cs, "hide").status_code, 400)  # a reason is required
        done = self.moderate(self.cs, "hide", note="Contains abuse")
        self.assertEqual(done.status_code, 200, done.data)
        self.assertEqual(done.data["status"], "HIDDEN")
        self.assertEqual(done.data["moderation_note"], "Contains abuse")
        data = APIClient().get(self.reviews_url()).data
        self.assertEqual(data["count"], 0)
        self.assertIsNone(data["summary"]["average"])
        rows = {r["name"]: r for r in APIClient().get("/api/products/").data["results"]}
        self.assertEqual(rows["Review Phone"]["review_count"], 0)

    def test_publishing_brings_it_back(self):
        self.moderate(self.cs, "hide", note="Check")
        self.assertEqual(self.moderate(self.cs, "publish").data["status"], "PUBLISHED")
        self.assertEqual(APIClient().get(self.reviews_url()).data["count"], 1)

    def test_a_hidden_review_can_no_longer_be_edited_by_its_author(self):
        self.moderate(self.cs, "hide", note="Policy")
        self.client.force_authenticate(self.alice)
        response = self.client.patch(f"/api/reviews/{self.review_id}/", {"rating": 1}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_only_moderators_can_moderate(self):
        self.assertEqual(self.moderate(self.pm, "hide", note="x").status_code, 403)  # can view, not change
        self.assertEqual(self.moderate(self.alice, "hide", note="x").status_code, 403)
        self.assertEqual(self.moderate(self.bob, "hide", note="x").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f"/api/admin/reviews/{self.review_id}/hide/", {}, format="json").status_code, 401)
        self.assertEqual(Review.objects.get().status, "PUBLISHED")

    def test_staff_list_shows_the_customer_and_hidden_reviews(self):
        self.moderate(self.cs, "hide", note="Check")
        self.client.force_authenticate(self.pm)
        data = self.client.get("/api/admin/reviews/?status=HIDDEN").data
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["customer"], "alice@example.com")
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.get("/api/admin/reviews/").status_code, 403)
