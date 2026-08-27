"""
Page Object Model for Sauce Demo Inventory Page.
Encapsulates product listing and cart interaction elements.
"""


class InventoryPage:
    """Inventory/products page of Sauce Demo."""

    # Locators
    PRODUCT_ITEM = ".inventory_item"
    PRODUCT_NAME = ".inventory_item_name"
    ADD_TO_CART_BUTTON = "button[data-test='add-to-cart-sauce-labs-backpack']"
    REMOVE_FROM_CART_BUTTON = "button[data-test='remove-sauce-labs-backpack']"
    CART_BADGE = ".shopping_cart_badge"
    CART_LINK = ".shopping_cart_link"
    SORT_DROPDOWN = "select[data-test='product_sort_container']"

    def __init__(self, page):
        """
        Initialize the inventory page.
        """
        self.page = page

    def navigate(self, url: str):
        """Navigate to inventory page."""
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")

    def get_products_count(self) -> int:
        """
        Get count of products displayed.
        """
        return self.page.locator(self.PRODUCT_ITEM).count()

    def get_product_names(self) -> list:
        """
        Get all product names.
        """
        return self.page.locator(self.PRODUCT_NAME).all_text_contents()

    def add_product_to_cart(self, product_button_locator: str):
        """
        Add a product to cart.
        """
        self.page.click(product_button_locator)

    def remove_product_from_cart(self, product_button_locator: str):
        """
        Remove a product from cart.
        """
        self.page.click(product_button_locator)

    def get_cart_badge_count(self) -> str:
        """
        Get the cart badge count.
        """
        badge = self.page.locator(self.CART_BADGE)
        return badge.text_content()

    def is_cart_badge_visible(self) -> bool:
        """Check if cart badge is visible."""
        return self.page.locator(self.CART_BADGE).is_visible()

    def click_cart(self):
        """Click on shopping cart icon."""
        self.page.click(self.CART_LINK)
        self.page.wait_for_load_state("networkidle")

    def sort_products(self, sort_option: str):
        """
        Sort products by option.
        """
        self.page.select_option(self.SORT_DROPDOWN, sort_option)
