from django.utils import timezone

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
            review = Review.objects.get(id=review_id, restaurant=restaurant)
        except (Restaurant.DoesNotExist, Review.DoesNotExist):
            return Response(
                {
                    "success": False,
                    "message": "Review not found",
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


class ReviewHelpfulView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, review_id):
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

        review.helpful_count += 1
        review.save(update_fields=["helpful_count"])

        return Response(
            {
                "success": True,
                "message": "Marked as helpful",
                "helpful_count": review.helpful_count,
            }
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