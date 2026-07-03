from django.utils import timezone
from math import ceil

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from accounts.models import User
from accounts.permissions import IsAdmin, IsRestaurant

from .models import Restaurant, RestaurantGallery, Review
from .serializers import (
    CreateRestaurantSerializer,
    GallerySerializer,
    RestaurantDetailSerializer,
    RestaurantListSerializer,
    UpdateRestaurantSerializer,
    AddReviewSerializer,
    RespondReviewSerializer,
    ReviewSerializer,
    AdminReviewSerializer,
    EditReviewSerializer,
    FlagReviewSerializer,
    ReviewResponseSerializer,
)


class AdminRestaurantListView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = Restaurant.objects.select_related("owner").all()

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)

        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(city__icontains=city)

        serializer = RestaurantListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "count": qs.count(),
                "data": serializer.data,
            }
        )


class AdminCreateRestaurantView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = CreateRestaurantSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        owner = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            full_name=data["owner_name"],
            phone_number=data.get("phone", ""),
            role="restaurant",
            is_email_verified=True,
        )

        restaurant = Restaurant.objects.create(
            owner=owner,
            name=data["restaurant_name"],
            address=data["location"],
            city=data.get("city", ""),
            phone=data.get("phone", ""),
            email=data["email"],
            description=data.get("description", ""),
            categories=data.get("categories", []),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            status="active",
        )

        return Response(
            {
                "success": True,
                "message": f"Restaurant '{restaurant.name}' created successfully",
                "data": RestaurantDetailSerializer(
                    restaurant,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminRestaurantDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, pk):
        try:
            return Restaurant.objects.select_related("owner").get(pk=pk)
        except Restaurant.DoesNotExist:
            return None

    def get(self, request, pk):
        restaurant = self.get_object(pk)

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "success": True,
                "data": RestaurantDetailSerializer(
                    restaurant,
                    context={"request": request},
                ).data,
            }
        )

    def put(self, request, pk):
        restaurant = self.get_object(pk)

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UpdateRestaurantSerializer(
            restaurant,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                {
                    "success": True,
                    "message": "Restaurant updated",
                    "data": RestaurantDetailSerializer(
                        restaurant,
                        context={"request": request},
                    ).data,
                }
            )

        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, pk):
        restaurant = self.get_object(pk)

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        owner = restaurant.owner

        restaurant.delete()
        owner.delete()

        return Response(
            {
                "success": True,
                "message": "Restaurant deleted",
            }
        )


class AdminSuspendRestaurantView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            restaurant = Restaurant.objects.select_related("owner").get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if restaurant.status == "suspended":
            restaurant.status = "active"
            restaurant.owner.is_suspended = False
            message = "Restaurant reactivated"
        else:
            restaurant.status = "suspended"
            restaurant.owner.is_suspended = True
            message = "Restaurant suspended"

        restaurant.save(update_fields=["status"])
        restaurant.owner.save(update_fields=["is_suspended"])

        return Response(
            {
                "success": True,
                "message": message,
            }
        )


class MyRestaurantView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_restaurant(self, user):
        try:
            return Restaurant.objects.get(owner=user)
        except Restaurant.DoesNotExist:
            return None

    def get(self, request):
        restaurant = self.get_restaurant(request.user)

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "success": True,
                "data": RestaurantDetailSerializer(
                    restaurant,
                    context={"request": request},
                ).data,
            }
        )

    def put(self, request):
        restaurant = self.get_restaurant(request.user)

        if not restaurant:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UpdateRestaurantSerializer(
            restaurant,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()

            return Response(
                {
                    "success": True,
                    "message": "Profile updated",
                    "data": RestaurantDetailSerializer(
                        restaurant,
                        context={"request": request},
                    ).data,
                }
            )

        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class MyRestaurantGalleryView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        image = request.FILES.get("image")

        if not image:
            return Response(
                {
                    "success": False,
                    "message": "Image is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        gallery_item = RestaurantGallery.objects.create(
            restaurant=restaurant,
            image=image,
        )

        return Response(
            {
                "success": True,
                "message": "Image added",
                "data": GallerySerializer(
                    gallery_item,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, image_id):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            image = RestaurantGallery.objects.get(
                id=image_id,
                restaurant=restaurant,
            )
        except (Restaurant.DoesNotExist, RestaurantGallery.DoesNotExist):
            return Response(
                {
                    "success": False,
                    "message": "Image not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        image.delete()

        return Response(
            {
                "success": True,
                "message": "Image removed",
            }
        )


class PublicRestaurantListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Restaurant.objects.filter(status="active")

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(city__icontains=city)

        category = request.query_params.get("category")
        if category:
            qs = qs.filter(categories__icontains=category)

        serializer = RestaurantListSerializer(
            qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "data": serializer.data,
            }
        )


class PublicRestaurantDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.prefetch_related(
                "gallery",
                "reviews__user",
            ).get(pk=pk, status="active")
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "success": True,
                "data": RestaurantDetailSerializer(
                    restaurant,
                    context={"request": request},
                ).data,
            }
        )


class ReviewListAddView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]

        return [IsAuthenticated()]

    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        reviews = restaurant.reviews.select_related("user").all()

        serializer = ReviewSerializer(
            reviews,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "data": serializer.data,
            }
        )

    def post(self, request, pk):
        if request.user.role != "user":
            return Response(
                {
                    "success": False,
                    "message": "Only customers can add reviews",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            restaurant = Restaurant.objects.get(pk=pk, status="active")
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if Review.objects.filter(restaurant=restaurant, user=request.user).exists():
            return Response(
                {
                    "success": False,
                    "message": "You already reviewed this restaurant",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AddReviewSerializer(data=request.data)

        if serializer.is_valid():
            review = serializer.save(
                restaurant=restaurant,
                user=request.user,
            )

            return Response(
                {
                    "success": True,
                    "message": "Review added",
                    "data": ReviewSerializer(
                        review,
                        context={"request": request},
                    ).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ReviewRespondView(APIView):
    permission_classes = [IsAuthenticated, IsRestaurant]

    def post(self, request, review_id):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            review = Review.objects.select_related("user", "restaurant").get(
                id=review_id,
                restaurant=restaurant,
            )
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Only restaurant accounts can respond to reviews.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found for your restaurant.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RespondReviewSerializer(data=request.data)

        if serializer.is_valid():
            review.restaurant_response = serializer.validated_data["response"]
            review.restaurant_response_date = timezone.now()
            review.save(
                update_fields=[
                    "restaurant_response",
                    "restaurant_response_date",
                ]
            )

            # Send notification to review owner/user
            try:
                from notifications.utils import create_notification

                create_notification(
                    user=review.user,
                    type="restaurant",
                    title="Restaurant Responded to Your Review",
                    message=f"{restaurant.name} responded to your review.",
                    related_restaurant=restaurant,
                    metadata={
                        "review_id": review.id,
                        "restaurant_id": restaurant.id,
                        "restaurant_name": restaurant.name,
                        "response": review.restaurant_response,
                    },
                )
            except Exception as e:
                print("Review response notification failed:", e)

            return Response(
                {
                    "success": True,
                    "message": "Response added",
                    "data": ReviewSerializer(
                        review,
                        context={"request": request},
                    ).data,
                }
            )

        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
class ReviewDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, review_id):
        try:
            review = Review.objects.get(id=review_id)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        review.delete()

        return Response(
            {
                "success": True,
                "message": "Review deleted",
            }
        )

def paginate_qs(qs, request, default_page_size=10, max_page_size=50):
    try:
        page = int(request.query_params.get("page", 1))
    except Exception:
        page = 1

    try:
        page_size = int(request.query_params.get("page_size", default_page_size))
    except Exception:
        page_size = default_page_size

    page = max(page, 1)
    page_size = max(1, min(page_size, max_page_size))

    count = qs.count()
    total_pages = max(1, ceil(count / page_size)) if count else 1

    if page > total_pages:
        page = total_pages

    start = (page - 1) * page_size
    end = start + page_size

    return qs[start:end], {
        "count": count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": end < count,
        "has_prev": page > 1,
    }


class RestaurantReviewListView(APIView):
    """
    GET /api/restaurants/<restaurant_id>/reviews/
    Public visible reviews only.
    """

    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk)
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found.",
                },
                status=404,
            )

        qs = (
            Review.objects.filter(
                restaurant=restaurant,
                is_hidden=False,
            )
            .select_related("user", "restaurant")
            .order_by("-created_at")
        )

        rating = request.query_params.get("rating")
        search = request.query_params.get("search")

        if rating:
            qs = qs.filter(rating=rating)

        if search:
            qs = qs.filter(
                Q(comment__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(deal__title__icontains=search)
            )

        page_qs, meta = paginate_qs(qs, request)

        serializer = ReviewSerializer(
            page_qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                **meta,
                "data": serializer.data,
                "results": serializer.data,
            }
        )


class AddRestaurantReviewView(APIView):
    """
    POST /api/restaurants/<restaurant_id>/reviews/add/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != "user":
            return Response(
                {
                    "success": False,
                    "message": "Only customers can add reviews.",
                },
                status=403,
            )

        try:
            restaurant = Restaurant.objects.get(pk=pk, status="active")
        except Restaurant.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Restaurant not found.",
                },
                status=404,
            )

        serializer = AddReviewSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=400,
            )

        if Review.objects.filter(
            restaurant=restaurant,
            user=request.user,
        ).exists():
            return Response(
                {
                    "success": False,
                    "message": "You already reviewed this restaurant.",
                },
                status=400,
            )

        review = Review.objects.create(
            restaurant=restaurant,
            user=request.user,
            rating=serializer.validated_data["rating"],
            comment=serializer.validated_data.get("comment", ""),
        )

        restaurant.update_rating()

        return Response(
            {
                "success": True,
                "message": "Review added successfully.",
                "data": ReviewSerializer(
                    review,
                    context={"request": request},
                ).data,
            },
            status=201,
        )

class EditMyReviewView(APIView):
    """
    PUT/PATCH /api/restaurants/reviews/<review_id>/edit/
    """

    permission_classes = [IsAuthenticated]

    def put(self, request, review_id):
        try:
            review = Review.objects.get(id=review_id, user=request.user)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        serializer = EditReviewSerializer(
            review,
            data=request.data,
            partial=True,
        )

        if serializer.is_valid():
            serializer.save()
            review.restaurant.update_rating()

            return Response(
                {
                    "success": True,
                    "message": "Review updated successfully.",
                    "data": ReviewSerializer(
                        review,
                        context={"request": request},
                    ).data,
                }
            )

        return Response(
            {
                "success": False,
                "errors": serializer.errors,
            },
            status=400,
        )

    def patch(self, request, review_id):
        return self.put(request, review_id)


class DeleteMyReviewView(APIView):
    """
    DELETE /api/restaurants/reviews/<review_id>/my-delete/
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, review_id):
        try:
            review = Review.objects.get(id=review_id, user=request.user)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        restaurant = review.restaurant
        review.delete()
        restaurant.update_rating()

        return Response(
            {
                "success": True,
                "message": "Review deleted successfully.",
            }
        )


class MyReviewsView(APIView):
    """
    GET /api/restaurants/reviews/my/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Review.objects.filter(user=request.user)
            .select_related("restaurant", "deal", "user")
            .order_by("-created_at")
        )

        rating = request.query_params.get("rating")
        search = request.query_params.get("search")

        if rating:
            qs = qs.filter(rating=rating)

        if search:
            qs = qs.filter(
                Q(comment__icontains=search)
                | Q(restaurant__name__icontains=search)
                | Q(deal__title__icontains=search)
            )

        page_qs, meta = paginate_qs(qs, request)

        serializer = ReviewSerializer(
            page_qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                **meta,
                "data": serializer.data,
                "results": serializer.data,
            }
        )


class FlagReviewView(APIView):
    """
    POST /api/restaurants/reviews/<review_id>/flag/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, review_id):
        try:
            review = Review.objects.select_related("restaurant").get(id=review_id)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        serializer = FlagReviewSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=400,
            )

        review.is_flagged = True
        review.flagged_reason = serializer.validated_data["reason"]
        review.save(update_fields=["is_flagged", "flagged_reason"])

        try:
            from notifications.utils import notify_admins

            notify_admins(
                type="system",
                title="Review Flagged",
                message=(
                    f"A review at {review.restaurant.name} was flagged. "
                    f"Reason: {review.flagged_reason}"
                ),
                related_restaurant=review.restaurant,
                metadata={
                    "review_id": review.id,
                    "reason": review.flagged_reason,
                },
            )
        except Exception:
            pass

        return Response(
            {
                "success": True,
                "message": "Review flagged for moderation.",
            }
        )


class ReviewHelpfulView(APIView):
    """
    POST /api/restaurants/reviews/<review_id>/helpful/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, review_id):
        try:
            review = Review.objects.get(id=review_id, is_hidden=False)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        review.helpful_count = (review.helpful_count or 0) + 1
        review.save(update_fields=["helpful_count"])

        return Response(
            {
                "success": True,
                "message": "Marked as helpful.",
                "helpful_count": review.helpful_count,
            }
        )


class RespondToReviewView(APIView):
    """
    POST /api/restaurants/reviews/<review_id>/respond/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, review_id):
        try:
            review = Review.objects.select_related("restaurant").get(id=review_id)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        is_admin = getattr(request.user, "role", "") == "admin"
        is_restaurant_owner = (
            getattr(request.user, "role", "") == "restaurant"
            and review.restaurant.owner_id == request.user.id
        )

        if not is_admin and not is_restaurant_owner:
            return Response(
                {
                    "success": False,
                    "message": "You do not have permission to respond to this review.",
                },
                status=403,
            )

        serializer = ReviewResponseSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "errors": serializer.errors,
                },
                status=400,
            )

        review.restaurant_response = serializer.validated_data["response"]
        review.restaurant_response_date = timezone.now()
        review.save(
            update_fields=[
                "restaurant_response",
                "restaurant_response_date",
            ]
        )

        try:
            from notifications.utils import create_notification

            create_notification(
                user=review.user,
                type="restaurant",
                title="Restaurant Responded to Your Review",
                message=f"{review.restaurant.name} responded to your review.",
                related_restaurant=review.restaurant,
                metadata={
                    "review_id": review.id,
                },
            )
        except Exception:
            pass

        return Response(
            {
                "success": True,
                "message": "Response added successfully.",
                "data": ReviewSerializer(
                    review,
                    context={"request": request},
                ).data,
            }
        )


class AdminReviewListView(APIView):
    """
    GET /api/restaurants/admin/reviews/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = (
            Review.objects.select_related("user", "restaurant")
            .all()
            .order_by("-created_at")
        )

        restaurant_id = request.query_params.get("restaurant")
        rating = request.query_params.get("rating")
        flagged = request.query_params.get("flagged")
        hidden = request.query_params.get("hidden")
        search = request.query_params.get("search")

        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)

        if rating:
            qs = qs.filter(rating=rating)

        if flagged == "true":
            qs = qs.filter(is_flagged=True)

        if hidden == "true":
            qs = qs.filter(is_hidden=True)

        if hidden == "false":
            qs = qs.filter(is_hidden=False)

        if search:
            qs = qs.filter(
                Q(comment__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(restaurant__name__icontains=search)
                | Q(deal__title__icontains=search)
            )

        page_qs, meta = paginate_qs(qs, request)

        serializer = AdminReviewSerializer(
            page_qs,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                **meta,
                "data": serializer.data,
                "results": serializer.data,
            }
        )


class AdminHideReviewView(APIView):
    """
    POST /api/restaurants/admin/reviews/<review_id>/hide/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, review_id):
        try:
            review = Review.objects.select_related("restaurant").get(id=review_id)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        review.is_hidden = not review.is_hidden
        review.save(update_fields=["is_hidden"])
        review.restaurant.update_rating()

        status_text = "hidden" if review.is_hidden else "visible"

        return Response(
            {
                "success": True,
                "message": f"Review is now {status_text}.",
                "is_hidden": review.is_hidden,
            }
        )


class AdminClearFlagView(APIView):
    """
    POST /api/restaurants/admin/reviews/<review_id>/clear-flag/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, review_id):
        try:
            review = Review.objects.get(id=review_id)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        review.is_flagged = False
        review.flagged_reason = ""
        review.save(update_fields=["is_flagged", "flagged_reason"])

        return Response(
            {
                "success": True,
                "message": "Flag cleared.",
            }
        )


class AdminDeleteReviewView(APIView):
    """
    DELETE /api/restaurants/admin/reviews/<review_id>/delete/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, review_id):
        try:
            review = Review.objects.select_related("restaurant").get(id=review_id)
        except Review.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Review not found.",
                },
                status=404,
            )

        restaurant = review.restaurant
        review.delete()
        restaurant.update_rating()

        return Response(
            {
                "success": True,
                "message": "Review deleted successfully.",
            }
        )