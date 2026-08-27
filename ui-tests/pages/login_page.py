"""
Page Object Model for Sauce Demo Login Page.
Encapsulates all login-related UI elements and interactions.
"""


class LoginPage:

    # Locators
    USERNAME_INPUT = "input[data-test='username']"
    PASSWORD_INPUT = "input[data-test='password']"
    LOGIN_BUTTON = "input[data-test='login-button']"
    ERROR_MESSAGE = "h3[data-test='error']"

    def __init__(self, page):
        """
        Initialize the login page.
        """
        self.page = page

    def navigate(self, url: str):
        """Navigate to the login page."""
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")

    def enter_username(self, username: str):
        """Enter username in the username field."""
        self.page.fill(self.USERNAME_INPUT, username)

    def enter_password(self, password: str):
        """Enter password in the password field."""
        self.page.fill(self.PASSWORD_INPUT, password)

    def click_login(self):
        """Click the login button."""
        self.page.click(self.LOGIN_BUTTON)
        self.page.wait_for_load_state("networkidle")

    def login(self, username: str, password: str):
        """
        Perform complete login flow.
        """
        self.enter_username(username)
        self.enter_password(password)
        self.click_login()

    def get_error_message(self) -> str:
        """
        Get error message displayed on login failure.
        """
        error_element = self.page.locator(self.ERROR_MESSAGE)
        error_element.wait_for()
        return error_element.text_content()

    def is_error_displayed(self) -> bool:
        """
        Check if error message is displayed.
        """
        return self.page.locator(self.ERROR_MESSAGE).is_visible()

    def is_username_field_visible(self) -> bool:
        """Check if username field is visible."""
        return self.page.locator(self.USERNAME_INPUT).is_visible()

    def is_password_field_visible(self) -> bool:
        """Check if password field is visible."""
        return self.page.locator(self.PASSWORD_INPUT).is_visible()
