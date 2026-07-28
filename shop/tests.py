from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal

from shop.models import Product, Cart, CartItem, Order, OrderItem, Category

User = get_user_model()


class CategoryModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Fresh Produce",
            description="Fresh farm produce",
        )

    def test_category_creation(self):
        self.assertEqual(self.category.name, "Fresh Produce")
        self.assertEqual(self.category.slug, "fresh-produce")
        self.assertEqual(self.category.products.count(), 0)

    def test_slug_auto_generated(self):
        category = Category.objects.create(name="Catfish", description="Fish category")
        self.assertEqual(category.slug, "catfish")

    def test_unique_slug_enforced(self):
        Category.objects.create(name="Catfish", slug="catfish")
        with self.assertRaises(Exception):
            Category.objects.create(name="Catfish Again", slug="catfish")

    def test_category_str(self):
        self.assertEqual(str(self.category), "Fresh Produce")

    def test_cascade_delete_products(self):
        product = Product.objects.create(
            name="Test Product",
            price=Decimal("1000.00"),
            stock_quantity=10,
            category=self.category,
        )
        self.assertEqual(Product.objects.count(), 1)
        self.category.delete()
        self.assertEqual(Product.objects.count(), 0)

    def test_is_sample_data_default_false(self):
        self.assertFalse(self.category.is_sample_data)


class ProductModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Fresh Produce",
            description="Fresh farm produce",
        )
        self.product = Product.objects.create(
            name="Fresh Tomatoes",
            description="Locally grown organic tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=50,
            category=self.category,
        )

    def test_product_creation(self):
        self.assertEqual(self.product.name, "Fresh Tomatoes")
        self.assertEqual(self.product.price, Decimal("1500.00"))
        self.assertTrue(self.product.in_stock)
        self.assertEqual(self.product.category.name, "Fresh Produce")

    def test_out_of_stock(self):
        self.product.stock_quantity = 0
        self.product.save()
        self.assertFalse(self.product.in_stock)

    def test_decrement_stock(self):
        self.product.decrement_stock(10)
        self.assertEqual(self.product.stock_quantity, 40)

    def test_decrement_stock_insufficient(self):
        with self.assertRaises(ValueError):
            self.product.decrement_stock(100)

    def test_increment_stock(self):
        self.product.increment_stock(10)
        self.assertEqual(self.product.stock_quantity, 60)

    def test_is_sample_data_default_false(self):
        self.assertFalse(self.product.is_sample_data)

    def test_product_str(self):
        self.assertEqual(str(self.product), "Fresh Tomatoes")


class CartModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            full_name="Test User",
            password="testpass123",
            username="testuser1",
        )
        self.product = Product.objects.create(
            name="Fresh Tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=50,
            category=Category.objects.create(name="Test Cat", description="Test"),
        )
        self.cart = Cart.objects.create(user=self.user)
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            product=self.product,
            quantity=3,
        )

    def test_cart_total(self):
        self.assertEqual(self.cart.total, Decimal("4500.00"))

    def test_cart_item_count(self):
        self.assertEqual(self.cart.item_count, 3)

    def test_cart_is_not_empty(self):
        self.assertFalse(self.cart.is_empty)

    def test_cart_is_empty(self):
        self.cart_item.delete()
        self.assertTrue(self.cart.is_empty)

    def test_cart_item_subtotal(self):
        self.assertEqual(self.cart_item.subtotal, Decimal("4500.00"))


class OrderModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            full_name="Test User",
            password="testpass123",
            username="testuser1",
        )
        self.product = Product.objects.create(
            name="Fresh Tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=50,
            category=Category.objects.create(name="Test Cat", description="Test"),
        )
        self.order = Order.objects.create(
            user=self.user,
            total=Decimal("3000.00"),
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            quantity=2,
            price=self.product.price,
        )

    def test_order_creation(self):
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.order.total, Decimal("3000.00"))

    def test_order_item_subtotal(self):
        self.assertEqual(self.order_item.subtotal, Decimal("3000.00"))

    def test_order_str(self):
        self.assertIn("Test User", str(self.order))
        self.assertIn("Pending", str(self.order))


class ShopViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            full_name="Test User",
            password="testpass123",
            username="testuser1",
        )
        self.product = Product.objects.create(
            name="Fresh Tomatoes",
            description="Organic tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=50,
            category=Category.objects.create(name="Test Cat", description="Test"),
        )
        self.out_of_stock_product = Product.objects.create(
            name="Out of Stock Item",
            price=Decimal("2000.00"),
            stock_quantity=0,
            category=Category.objects.create(name="Test Cat2", description="Test"),
        )

    def test_product_list_page(self):
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fresh Tomatoes")
        self.assertContains(response, "Out of Stock Item")

    def test_cart_page_empty(self):
        response = self.client.get(reverse("shop:cart"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your cart is empty")

    def test_add_to_cart_authenticated(self):
        self.client.login(email="test@example.com", password="testpass123")
        response = self.client.post(
            reverse("shop:add_to_cart", args=[self.product.pk])
        )
        self.assertRedirects(response, reverse("shop:product_list"))
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.item_count, 1)

    def test_add_to_cart_anonymous(self):
        response = self.client.post(
            reverse("shop:add_to_cart", args=[self.product.pk])
        )
        self.assertRedirects(response, reverse("shop:product_list"))

    def test_add_out_of_stock_product(self):
        response = self.client.post(
            reverse("shop:add_to_cart", args=[self.out_of_stock_product.pk])
        )
        self.assertRedirects(response, reverse("shop:product_list"))

    def test_remove_from_cart(self):
        self.client.login(email="test@example.com", password="testpass123")
        self.client.post(reverse("shop:add_to_cart", args=[self.product.pk]))
        cart = Cart.objects.get(user=self.user)
        item = cart.items.first()
        response = self.client.post(reverse("shop:remove_from_cart", args=[item.pk]))
        self.assertRedirects(response, reverse("shop:cart"))
        self.assertTrue(cart.is_empty)

    def test_update_cart_item_quantity(self):
        self.client.login(email="test@example.com", password="testpass123")
        self.client.post(reverse("shop:add_to_cart", args=[self.product.pk]))
        cart = Cart.objects.get(user=self.user)
        item = cart.items.first()
        response = self.client.post(
            reverse("shop:update_cart_item", args=[item.pk]),
            {"quantity": 5},
        )
        self.assertRedirects(response, reverse("shop:cart"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

    def test_checkout_creates_order(self):
        self.client.login(email="test@example.com", password="testpass123")
        self.client.post(reverse("shop:add_to_cart", args=[self.product.pk]))
        response = self.client.get(reverse("shop:checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Checkout")
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total, Decimal("1500.00"))
        self.assertEqual(order.items.count(), 1)

    def test_checkout_empty_cart(self):
        self.client.login(email="test@example.com", password="testpass123")
        response = self.client.get(reverse("shop:checkout"))
        self.assertRedirects(response, reverse("shop:cart"))

    def test_cart_total_display(self):
        self.client.login(email="test@example.com", password="testpass123")
        self.client.post(reverse("shop:add_to_cart", args=[self.product.pk]))
        response = self.client.get(reverse("shop:cart"))
        self.assertContains(response, "1500.00")


class CategoryCRUDTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password="AdminPass123!",
            username="adminuser1",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )

    def login(self):
        return self.client.login(email=self.user.email, password="AdminPass123!")

    def test_category_create_view_get(self):
        self.login()
        response = self.client.get(reverse("admin_dashboard:product_category_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add Category")

    def test_category_create_view_post(self):
        self.login()
        response = self.client.post(
            reverse("admin_dashboard:product_category_add"),
            {"name": "Catfish", "description": "Fresh catfish products"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Category.objects.filter(name="Catfish").exists())

    def test_category_edit_view(self):
        self.login()
        category = Category.objects.create(name="Tilapia", description="Tilapia products")
        response = self.client.get(
            reverse("admin_dashboard:product_category_edit", args=[category.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Category")

        response = self.client.post(
            reverse("admin_dashboard:product_category_edit", args=[category.pk]),
            {"name": "Tilapia", "description": "Updated description"}
        )
        self.assertEqual(response.status_code, 302)
        category.refresh_from_db()
        self.assertEqual(category.description, "Updated description")

    def test_category_delete_view_get(self):
        self.login()
        category = Category.objects.create(name="ToDelete", description="Will be deleted")
        response = self.client.get(
            reverse("admin_dashboard:product_category_delete", args=[category.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete Category")

    def test_category_delete_cascades_to_products(self):
        self.login()
        category = Category.objects.create(name="ToDelete", description="Will be deleted")
        Product.objects.create(
            name="Product A",
            price=Decimal("1000.00"),
            stock_quantity=5,
            category=category,
        )
        Product.objects.create(
            name="Product B",
            price=Decimal("2000.00"),
            stock_quantity=3,
            category=category,
        )
        self.assertEqual(Product.objects.count(), 2)

        response = self.client.post(
            reverse("admin_dashboard:product_category_delete", args=[category.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())
        self.assertEqual(Product.objects.count(), 0)


class ProductCRUDTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="admin@example.com",
            full_name="Admin User",
            password="AdminPass123!",
            username="adminuser1",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.category = Category.objects.create(name="Catfish", description="Catfish products")

    def login(self):
        return self.client.login(email=self.user.email, password="AdminPass123!")

    def test_product_create_view_get(self):
        self.login()
        response = self.client.get(reverse("admin_dashboard:product_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add Product")

    def test_product_create_view_post(self):
        self.login()
        response = self.client.post(
            reverse("admin_dashboard:product_add"),
            {
                "name": "Live Catfish",
                "category": self.category.pk,
                "price": 3500,
                "stock_quantity": 20,
                "description": "Fresh live catfish",
                "is_active": True,
            }
        )
        self.assertEqual(response.status_code, 302)
        product = Product.objects.first()
        self.assertEqual(product.name, "Live Catfish")
        self.assertEqual(product.category.name, "Catfish")
        self.assertTrue(product.is_active)

    def test_product_edit_view(self):
        self.login()
        product = Product.objects.create(
            name="Old Name",
            price=Decimal("1000.00"),
            stock_quantity=5,
            category=self.category,
        )
        response = self.client.get(
            reverse("admin_dashboard:product_edit", args=[product.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Product")

        response = self.client.post(
            reverse("admin_dashboard:product_edit", args=[product.pk]),
            {
                "name": "New Name",
                "category": self.category.pk,
                "price": 1500,
                "stock_quantity": 10,
                "description": "Updated description",
                "is_active": True,
            }
        )
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.name, "New Name")
        self.assertEqual(product.price, Decimal("1500.00"))

    def test_product_delete_view(self):
        self.login()
        product = Product.objects.create(
            name="ToDelete",
            price=Decimal("1000.00"),
            stock_quantity=5,
            category=self.category,
        )
        response = self.client.post(
            reverse("admin_dashboard:product_delete", args=[product.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())


class SampleDataTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="SuperPass123!",
            username="superadmin1",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.farm_manager = User.objects.create_user(
            email="farmmanager@example.com",
            full_name="Farm Manager",
            password="ManagerPass123!",
            username="manager1",
            role=User.Role.FARM_MANAGER,
        )
        Category.objects.filter(is_sample_data=True).delete()
        Product.objects.filter(is_sample_data=True).delete()

    def test_populate_sample_data_creates_categories_and_products(self):
        self.client.login(email=self.super_admin.email, password="SuperPass123!")
        response = self.client.post(
            reverse("admin_dashboard:populate_sample_data"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertGreater(data['categories_created'], 0)
        self.assertGreater(data['products_created'], 0)

        self.assertGreater(Category.objects.filter(is_sample_data=True).count(), 0)
        self.assertGreater(Product.objects.filter(is_sample_data=True).count(), 0)

    def test_populate_sample_data_requires_super_admin(self):
        self.client.login(email=self.farm_manager.email, password="ManagerPass123!")
        response = self.client.post(
            reverse("admin_dashboard:populate_sample_data"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_sample_data_removes_only_flagged_items(self):
        self.client.login(email=self.super_admin.email, password="SuperPass123!")
        
        real_category = Category.objects.create(name="Real Category", description="Real")
        real_product = Product.objects.create(
            name="Real Product",
            price=Decimal("1000.00"),
            stock_quantity=10,
            category=real_category,
        )

        sample_category = Category.objects.create(
            name="Sample Cat",
            description="Sample",
            is_sample_data=True,
        )
        sample_product = Product.objects.create(
            name="Sample Product",
            price=Decimal("500.00"),
            stock_quantity=5,
            category=sample_category,
            is_sample_data=True,
        )

        initial_category_count = Category.objects.count()
        initial_product_count = Product.objects.count()

        response = self.client.post(
            reverse("admin_dashboard:delete_sample_data"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['categories_deleted'], 1)
        self.assertEqual(data['products_deleted'], 1)

        self.assertFalse(Category.objects.filter(pk=sample_category.pk).exists())
        self.assertFalse(Product.objects.filter(pk=sample_product.pk).exists())
        self.assertTrue(Category.objects.filter(pk=real_category.pk).exists())
        self.assertTrue(Product.objects.filter(pk=real_product.pk).exists())
        self.assertEqual(Category.objects.count(), initial_category_count - 1)
        self.assertEqual(Product.objects.count(), initial_product_count - 1)

    def test_delete_sample_data_requires_super_admin(self):
        self.client.login(email=self.farm_manager.email, password="ManagerPass123!")
        response = self.client.post(
            reverse("admin_dashboard:delete_sample_data"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)


class ShopPageCategoryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category1 = Category.objects.create(name="Catfish", description="Catfish products")
        self.category2 = Category.objects.create(name="Tilapia", description="Tilapia products")
        self.product1 = Product.objects.create(
            name="Live Catfish",
            price=Decimal("3500.00"),
            stock_quantity=20,
            category=self.category1,
            is_active=True,
        )
        self.product2 = Product.objects.create(
            name="Whole Tilapia",
            price=Decimal("2200.00"),
            stock_quantity=15,
            category=self.category2,
            is_active=True,
        )
        self.out_of_stock_product = Product.objects.create(
            name="Out of Stock Fish",
            price=Decimal("1000.00"),
            stock_quantity=0,
            category=self.category1,
            is_active=True,
        )

    def test_product_list_page_shows_categories(self):
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Catfish")
        self.assertContains(response, "Tilapia")

    def test_product_list_page_shows_products(self):
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Catfish")
        self.assertContains(response, "Whole Tilapia")
        self.assertContains(response, "Out of Stock Fish")

    def test_out_of_stock_shows_unavailable(self):
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unavailable")

    def test_products_grouped_by_category_in_context(self):
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertIn('products_by_category', context)
        products_by_category = context['products_by_category']
        self.assertIn('Catfish', products_by_category)
        self.assertIn('Tilapia', products_by_category)
        self.assertEqual(len(products_by_category['Catfish']), 2)
        self.assertEqual(len(products_by_category['Tilapia']), 1)
