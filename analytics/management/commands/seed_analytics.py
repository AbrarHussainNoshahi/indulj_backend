import random
import string
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.db import transaction

from accounts.models import User
from restaurants.models import Restaurant
from deals.models import Deal
from happy_hours.models import HappyHour
from orders.models import Order

try:
    from restaurants.models import Review
    HAS_REVIEW = True
except ImportError:
    HAS_REVIEW = False


RESTAURANT_NAMES = [
    "The Golden Fork", "Bella Napoli", "Sakura Garden", "El Rancho Grill",
    "The Brisket House", "Lotus Wok", "Papa's Kitchen", "The Rusty Anchor",
    "Verde Kitchen", "Spice Route", "Burger Republic", "La Belle Époque",
    "Seoul Bowl", "The Taco Stand", "Ocean Breeze Bistro", "Mama Rosa's",
    "The Noodle Bar", "Sunset Steakhouse", "Cafe Lumiere", "Dragon Palace",
    "The Copper Pot", "Ivy & Ember", "Saltwater Grill", "Casa Fuego",
    "The Velvet Spoon",
]

CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Miami",
    "Austin", "Seattle", "Denver", "Nashville", "Portland",
    "Atlanta", "Boston", "Phoenix", "San Diego", "Dallas",
]

DEAL_TITLES = [
    "2-for-1 Burgers", "Happy Hour Cocktails 50% Off",
    "Free Dessert with Entree", "Lunch Special $12",
    "Family Meal Deal", "Date Night Package",
    "Student Discount 20%", "Weekend Brunch Bundle",
    "Taco Tuesday Special", "Buy 1 Get 1 Pizza",
    "Chef's Tasting Menu", "Sunday Roast Deal",
    "Kids Eat Free", "Early Bird Dinner",
    "Pasta Night Special", "Sushi Rolling Special",
    "BBQ Feast Deal", "Vegan Menu 15% Off",
    "Craft Beer & Wings", "Bottomless Mimosas Brunch",
]

DEAL_DESCRIPTIONS = [
    "Limited time offer - do not miss out!",
    "Available every day while stocks last.",
    "Perfect for groups and families.",
    "Our most popular deal of the season.",
    "Book in advance to guarantee your spot.",
]

HH_NAMES = [
    "Evening Wind-Down", "After-Work Specials", "Sunset Happy Hour",
    "Midweek Mixer", "Friday Kickoff", "Late Night Bites",
    "Power Lunch Hour", "Weekend Warm-Up", "Thirsty Thursday",
    "Monday Blues Buster",
]

HH_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

REVIEW_TEXTS = [
    "Absolutely loved it! Will definitely come back.",
    "Great food, friendly staff. Highly recommend.",
    "Good value for money. The burger was excellent.",
    "Decent place - nothing extraordinary but solid.",
    "A bit noisy but the food made up for it.",
    "Amazing atmosphere and the cocktails were superb.",
    "Service was a little slow but the pasta was divine.",
    "Hidden gem! One of the best meals I have had.",
    "The happy hour deals are unbeatable in this area.",
    "Nice vibe, fresh ingredients. Would return.",
]


def rand_dt(months_back):
    now = timezone.now()
    lo  = now - timedelta(days=months_back * 30)
    delta_secs = int((now - lo).total_seconds())
    return lo + timedelta(seconds=random.randint(0, max(delta_secs, 1)))


def spread_over_months(months):
    created    = rand_dt(months)
    updated_at = created + timedelta(minutes=random.randint(10, 120))
    return created, updated_at


class Command(BaseCommand):
    help = "Seed the database with historical analytics data."

    def add_arguments(self, parser):
        parser.add_argument("--months",      type=int, default=6)
        parser.add_argument("--restaurants", type=int, default=12)
        parser.add_argument("--orders",      type=int, default=400)
        parser.add_argument("--users",       type=int, default=100)
        parser.add_argument("--clear",       action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        months        = options["months"]
        n_restaurants = options["restaurants"]
        n_orders      = options["orders"]
        n_users       = options["users"]

        if options["clear"]:
            self._clear()

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n Seeding {} months of analytics data...\n".format(months)
        ))

        self._ensure_admin()
        users       = self._seed_users(n_users, months)
        restaurants = self._seed_restaurants(n_restaurants)
        deals       = self._seed_deals(restaurants, months)
        hh_list     = self._seed_happy_hours(restaurants, months)
        self._seed_orders(restaurants, deals, hh_list, users, n_orders, months)

        if HAS_REVIEW:
            self._seed_reviews(restaurants, users, months)

        self.stdout.write(self.style.SUCCESS(
            "\nDone!\n"
            "   users        -> {}\n"
            "   restaurants  -> {}\n"
            "   deals        -> {}\n"
            "   happy hours  -> {}\n"
            "   orders       -> {}\n".format(n_users, n_restaurants, len(deals), len(hh_list), n_orders)
        ))

    def _ensure_admin(self):
        obj, created = User.objects.get_or_create(
            email="seed_admin@example.com",
            defaults={
                "full_name":    "Seed Admin",
                "role":         "admin",
                "is_staff":     True,
                "is_superuser": True,
                "password":     make_password("Admin1234!"),
                "referral_code": "SEEDADMIN",
            },
        )
        if created:
            self.stdout.write("  Admin: seed_admin@example.com  /  Admin1234!")

    def _seed_users(self, count, months):
        existing = list(User.objects.filter(email__startswith="seed_user_"))
        needed   = count - len(existing)

        if needed <= 0:
            self.stdout.write("  {} users already exist".format(len(existing)))
            return existing

        base = len(existing)
        bulk = []
        for i in range(base, base + needed):
            joined = rand_dt(months)
            bulk.append(User(
                full_name   = "Seed User {}".format(i),
                email       = "seed_user_{}@example.com".format(i),
                password    = make_password("Pass1234!"),
                role        = "user",
                date_joined = joined,
                referral_code = "SEEDUSER{:04d}".format(i),
            ))

        User.objects.bulk_create(bulk, ignore_conflicts=True)
        all_users = list(User.objects.filter(email__startswith="seed_user_"))
        self.stdout.write("  {} users ready".format(len(all_users)))
        return all_users

    def _seed_restaurants(self, count):
        existing = list(Restaurant.objects.filter(
            owner__email__startswith="seed_owner_"
        ))
        needed = count - len(existing)

        if needed <= 0:
            self.stdout.write("  {} restaurants already exist".format(len(existing)))
            return existing

        base  = len(existing)
        names = (RESTAURANT_NAMES * 10)[:needed]

        for i, name in enumerate(names):
            idx   = base + i
            email = "seed_owner_{}@example.com".format(idx)

            owner, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": "Seed Owner {}".format(idx),
                    "role":     "restaurant",
                    "password": make_password("Pass1234!"),
                    "referral_code": "SEEDOWNER{:04d}".format(idx),
                },
            )

            Restaurant.objects.get_or_create(
                owner=owner,
                defaults={
                    "name":   name,
                    "city":   random.choice(CITIES),
                    "address": "123 Main St, " + random.choice(CITIES),
                    "status": "active",
                    "rating": round(random.uniform(3.2, 5.0), 1),
                },
            )

        all_restaurants = list(Restaurant.objects.filter(
            owner__email__startswith="seed_owner_"
        ))
        self.stdout.write("  {} restaurants ready".format(len(all_restaurants)))
        return all_restaurants

    def _seed_deals(self, restaurants, months):
        status_pool = (
            ["active"]    * 5
            + ["expired"]   * 3
            + ["pending"]   * 2
            + ["draft"]     * 1
            + ["cancelled"] * 1
            + ["rejected"]  * 1
        )

        bulk = []
        for restaurant in restaurants:
            n = random.randint(4, 9)
            for _ in range(n):
                created_at, _ = spread_over_months(months)
                bulk.append(Deal(
                    restaurant        = restaurant,
                    title             = random.choice(DEAL_TITLES),
                    description       = random.choice(DEAL_DESCRIPTIONS),
                    status            = random.choice(status_pool),
                    views_count       = random.randint(10, 900),
                    redemptions_count = random.randint(0, 200),
                    created_at        = created_at,
                    price             = Decimal(str(round(random.uniform(5.0, 50.0), 2))),
                ))

        Deal.objects.bulk_create(bulk, ignore_conflicts=True)
        deals = list(Deal.objects.filter(restaurant__in=restaurants))
        self.stdout.write("  {} deals ready".format(len(deals)))
        return deals

    def _seed_happy_hours(self, restaurants, months):
        status_pool = (
            ["active"]    * 3
            + ["upcoming"]  * 3
            + ["expired"]   * 2
            + ["pending"]   * 2
            + ["cancelled"] * 1
            + ["rejected"]  * 1
        )

        bulk = []
        for restaurant in restaurants:
            n = random.randint(3, 6)
            for _ in range(n):
                created_at, _ = spread_over_months(months)
                days = random.sample(HH_DAYS, random.randint(1, 4))
                bulk.append(HappyHour(
                    restaurant   = restaurant,
                    title        = random.choice(HH_NAMES),
                    status       = random.choice(status_pool),
                    start_time   = "17:00",
                    end_time     = "21:00",
                    days_of_week = days,
                    created_at   = created_at,
                ))

        HappyHour.objects.bulk_create(bulk, ignore_conflicts=True)
        hh_list = list(HappyHour.objects.filter(restaurant__in=restaurants))
        self.stdout.write("  {} happy hours ready".format(len(hh_list)))
        return hh_list

    def _seed_orders(self, restaurants, deals, hh_list, users, total, months):
        if not users:
            self.stdout.write(self.style.WARNING("  No users - skipping orders"))
            return

        status_pool = (
            ["completed"] * 6
            + ["confirmed"]  * 2
            + ["pending"]    * 1
            + ["cancelled"]  * 1
        )

        deals_by_r = {}
        for d in deals:
            deals_by_r.setdefault(d.restaurant_id, []).append(d)

        hh_by_r = {}
        for hh in hh_list:
            hh_by_r.setdefault(hh.restaurant_id, []).append(hh)

        bulk = []
        generated_numbers = set()
        for _ in range(total):
            restaurant             = random.choice(restaurants)
            user                   = random.choice(users)
            status                 = random.choice(status_pool)
            amount                 = Decimal(str(round(random.uniform(8.0, 150.0), 2)))
            created_at, updated_at = spread_over_months(months)

            # Generate unique order number
            while True:
                digits = "".join(random.choices(string.digits, k=6))
                number = f"ORD-{digits}"
                if number not in generated_numbers:
                    generated_numbers.add(number)
                    break

            deal       = None
            happy_hour = None
            order_type = "deal"

            roll = random.random()
            if roll < 0.35 and deals_by_r.get(restaurant.id):
                deal = random.choice(deals_by_r[restaurant.id])
                order_type = "deal"
            elif roll < 0.60 and hh_by_r.get(restaurant.id):
                happy_hour = random.choice(hh_by_r[restaurant.id])
                order_type = "happy_hour"
            else:
                order_type = random.choice(["deal", "happy_hour"])

            items_list = [
                {
                    "name": random.choice(["Gourmet Burger", "Napoli Pizza", "Sushi Combo", "Steak & Chips", "Pasta Carbonara"]),
                    "quantity": random.randint(1, 2),
                    "price": float(amount),
                }
            ]

            bulk.append(Order(
                order_number = number,
                restaurant   = restaurant,
                user         = user,
                status       = status,
                total_amount = amount,
                deal         = deal,
                happy_hour   = happy_hour,
                order_type   = order_type,
                items        = items_list,
                created_at   = created_at,
                updated_at   = updated_at,
            ))

            if len(bulk) >= 500:
                Order.objects.bulk_create(bulk)
                bulk = []

        if bulk:
            Order.objects.bulk_create(bulk)

        self.stdout.write("  {} orders ready".format(total))

    def _seed_reviews(self, restaurants, users, months):
        if not users:
            return

        bulk = []
        for restaurant in restaurants:
            chosen_users = random.sample(users, min(len(users), random.randint(6, 20)))
            for user in chosen_users:
                created_at, _ = spread_over_months(months)
                bulk.append(Review(
                    restaurant = restaurant,
                    user       = user,
                    rating     = random.choices(
                        [3, 4, 5],
                        weights=[1, 3, 5],
                    )[0],
                    comment    = random.choice(REVIEW_TEXTS),
                    created_at = created_at,
                ))

        Review.objects.bulk_create(bulk, ignore_conflicts=True)
        self.stdout.write("  {} reviews ready".format(len(bulk)))

    def _clear(self):
        self.stdout.write(self.style.WARNING("\nClearing previously seeded data..."))

        seed_owners      = User.objects.filter(email__startswith="seed_owner_")
        seed_restaurants = Restaurant.objects.filter(owner__in=seed_owners)
        seed_users       = User.objects.filter(email__startswith="seed_user_")

        Order.objects.filter(restaurant__in=seed_restaurants).delete()

        if HAS_REVIEW:
            from restaurants.models import Review
            Review.objects.filter(restaurant__in=seed_restaurants).delete()

        HappyHour.objects.filter(restaurant__in=seed_restaurants).delete()
        Deal.objects.filter(restaurant__in=seed_restaurants).delete()
        seed_restaurants.delete()
        seed_users.delete()
        seed_owners.delete()
        User.objects.filter(email="seed_admin@example.com").delete()

        self.stdout.write(self.style.WARNING("  Cleared\n"))
