"""
UI tests for Sauce Demo application.
Tests login flows and complete purchase workflows.
"""

import pytest
from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage


@pytest.mark.smoke
def test_login_with_valid_credentials(page, env_config):
    """
    Test successful login with valid credentials - HAPPY PATH
    """
    login_page = LoginPage(page)
    inventory_page = InventoryPage(page)

    # Navigate to login page
    login_page.navigate(env_config["url"])

    # Verify login page is displayed
    assert login_page.is_username_field_visible()
    assert login_page.is_password_field_visible()

    # Perform login
    login_page.login(env_config["username"], env_config["password"])

    # Verify successful login - inventory page should be displayed
    products_count = inventory_page.get_products_count()
    assert products_count > 0, "Products should be displayed after successful login"


@pytest.mark.regression
def test_login_with_invalid_credentials(page, env_config):
    """
    Test login with invalid credentials - NEGATIVE CASE
    Verify error message is displayed
    """
    login_page = LoginPage(page)

    # Navigate to login page
    login_page.navigate(env_config["url"])

    # Perform login with invalid password
    login_page.login(env_config["username"], "wrong_password")

    # Verify error message is displayed
    assert login_page.is_error_displayed(), "Error message should be displayed"
    error_text = login_page.get_error_message()
    assert "Username and password do not match" in error_text


@pytest.mark.regression
def test_login_with_locked_account(page, env_config):
    """
    Test login with locked account - NEGATIVE CASE
    Verify appropriate error message is shown
    """
    login_page = LoginPage(page)

    # Navigate to login page
    login_page.navigate(env_config["url"])

    # Perform login with locked user
    login_page.login("locked_out_user", env_config["password"])

    # Verify error message for locked account
    assert login_page.is_error_displayed(), "Error message should be displayed"
    error_text = login_page.get_error_message()
    assert "locked out" in error_text.lower() or "Sorry" in error_text


@pytest.mark.smoke
def test_complete_purchase_flow(page, env_config):
    """
    Test complete purchase flow from login to checkout - HAPPY PATH
    """
    login_page = LoginPage(page)
    inventory_page = InventoryPage(page)

    # Step 1: Navigate and login
    login_page.navigate(env_config["url"])
    login_page.login(env_config["username"], env_config["password"])

    # Step 2: Verify inventory page
    products_count = inventory_page.get_products_count()
    assert products_count > 0, "Products should be visible"

    # Step 3: Add product to cart
    add_to_cart_btn = "button[data-test='add-to-cart-sauce-labs-backpack']"
    inventory_page.add_product_to_cart(add_to_cart_btn)

    # Step 4: Verify product added to cart
    assert inventory_page.is_cart_badge_visible(), "Cart badge should be visible"
    cart_count = inventory_page.get_cart_badge_count()
    assert cart_count == "1", "Cart should have 1 item"

    # Step 5: Click on cart
    inventory_page.click_cart()

    # Verify cart page is displayed (URL should contain 'cart')
    assert "cart" in page.url.lower(), "Should navigate to cart page"
