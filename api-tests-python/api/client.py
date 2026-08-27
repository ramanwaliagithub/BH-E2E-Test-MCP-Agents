"""
Reusable HTTP Client for API testing
Wrapper around requests library for consistent request/response handling
"""

import requests
from typing import Dict, Any, Optional


class Response:
    """
    Standardized Response object for consistent handling across tests
    """

    def __init__(self, status_code: int, data: Any, headers: Dict):
        self.status_code = status_code
        self.data = data
        self.headers = headers
        self.is_success = 200 <= status_code < 300


class HTTPClient:
    """
    HTTP Client for making REST API calls with consistent configuration
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 10,
        custom_headers: Optional[Dict] = None,
    ):
        """
        Initialize HTTP Client
        Args:
            base_url: Base URL for all API requests
            timeout: Request timeout in seconds (default: 10)
            custom_headers: Additional headers to include in all requests (default: None)
        """
        self.base_url = base_url
        self.timeout = timeout
        self.headers = custom_headers or {}
        self.session = requests.Session()
        # Set default headers
        if self.headers:
            self.session.headers.update(self.headers)

    def get(self, path: str, params: Optional[Dict] = None) -> Response:
        """
        Make GET request
        Args:
            path: API endpoint path
            params: Query parameters (default: None)

        Returns:
            Response object with status_code, data, headers, is_success
        """
        try:
            url = f"{self.base_url}{path}"
            response = self.session.get(url, params=params, timeout=self.timeout)
            return Response(
                status_code=response.status_code,
                data=response.json() if response.text else {},
                headers=dict(response.headers),
            )
        except Exception as e:
            raise Exception(f"GET request failed: {str(e)}")

    def post(
        self, path: str, data: Optional[Dict] = None, json: Optional[Dict] = None
    ) -> Response:
        """
        Make POST request
        Args:
            path: API endpoint path
            data: Form data (default: None)
            json: JSON data (default: None)
        Returns:
            Response object with status_code, data, headers, is_success
        """
        try:
            url = f"{self.base_url}{path}"
            response = self.session.post(
                url, data=data, json=json, timeout=self.timeout
            )
            return Response(
                status_code=response.status_code,
                data=response.json() if response.text else {},
                headers=dict(response.headers),
            )
        except Exception as e:
            raise Exception(f"POST request failed: {str(e)}")

    def put(self, path: str, data: Optional[Dict] = None, json: Optional[Dict] = None) -> Response:
        """
        Make PUT request
        Args:
            path: API endpoint path
            data: Form data (default: None)
            json: JSON data (default: None)
        Returns:
            Response object with status_code, data, headers, is_success
        """
        try:
            url = f"{self.base_url}{path}"
            response = self.session.put(
                url, data=data, json=json, timeout=self.timeout
            )
            return Response(
                status_code=response.status_code,
                data=response.json() if response.text else {},
                headers=dict(response.headers),
            )
        except Exception as e:
            raise Exception(f"PUT request failed: {str(e)}")

    def delete(self, path: str) -> Response:
        """
        Make DELETE request
        Args:
            path: API endpoint path
        Returns:
            Response object with status_code, data, headers, is_success
        """
        try:
            url = f"{self.base_url}{path}"
            response = self.session.delete(url, timeout=self.timeout)
            return Response(
                status_code=response.status_code,
                data=response.json() if response.text else {},
                headers=dict(response.headers),
            )
        except Exception as e:
            raise Exception(f"DELETE request failed: {str(e)}")

    def close(self):
        """Close the session"""
        self.session.close()
