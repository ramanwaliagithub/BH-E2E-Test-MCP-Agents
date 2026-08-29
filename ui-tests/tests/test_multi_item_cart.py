"""
UI test for adding multiple products to the cart on Sauce Demo.
"""

import pytest
from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage


@pytest.mark.regression
def test_add_multiple_items_to_cart(page, env_config):
    """
    Test adding two different products to the cart and verifying the cart
    badge reflects both - HAPPY PATH
    """
    login_page = LoginPage(page)
    inventory_page = InventoryPage(page)

    # Step 1: Navigate and login
    login_page.navigate(env_config["url"])
    login_page.login(env_config["username"], env_config["password"])

    # Step 2: Add the Sauce Labs Backpack to the cart
    backpack_btn = "button[data-test='add-to-cart-sauce-labs-backpack']"
    inventory_page.add_product_to_cart(backpack_btn)

    # Step 3: Add the Sauce Labs Bike Light to the cart
    bike_light_btn = "button[data-test='add-to-cart-sauce-labs-bike-light']"
    inventory_page.add_product_to_cart(bike_light_btn)

    # Step 4: Verify the cart badge shows both items
    assert inventory_page.is_cart_badge_visible(), "Cart badge should be visible"
    cart_count = inventory_page.get_cart_badge_count()
    assert cart_count == "2", "Cart should have 2 items"
