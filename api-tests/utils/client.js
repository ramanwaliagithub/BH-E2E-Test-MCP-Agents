/**
 * Reusable HTTP Client for API Testing
 * Wrapper around axios for consistent API testing operations
 */

const axios = require('axios');

class HTTPClient {
  /**
   * Initialize HTTP Client with base configuration
   * @param {string} baseURL - Base URL for API requests
   * @param {number} timeout - Request timeout in milliseconds (default: 10000)
   * @param {object} customHeaders - Additional custom headers (optional)
   */
  constructor(baseURL, timeout = 10000, customHeaders = {}) {
    this.baseURL = baseURL;
    this.timeout = timeout;
    this.headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      ...customHeaders,
    };

    // Creating axios instance with default config
    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: this.timeout,
      headers: this.headers,
    });
  }

  /**
   * Setting a custom header
   * @param {string} key - Header key
   * @param {string} value - Header value
   */
  setHeader(key, value) {
    this.headers[key] = value;
    this.client.defaults.headers.common[key] = value;
  }

  /**
   * GET request
   * @param {string} path - Endpoint path
   * @param {object} config - Additional axios config
   * @returns {Promise} Response object
   */
  async get(path, config = {}) {
    try {
      const response = await this.client.get(path, config);
      return this._formatResponse(response);
    } catch (error) {
      return this._handleError(error);
    }
  }

  /**
   * POST request
   * @param {string} path - Endpoint path
   * @param {object} data - Request body data
   * @param {object} config - Additional axios config
   * @returns {Promise} Response object
   */
  async post(path, data = {}, config = {}) {
    try {
      const response = await this.client.post(path, data, config);
      return this._formatResponse(response);
    } catch (error) {
      return this._handleError(error);
    }
  }

  /**
   * PUT request
   * @param {string} path - Endpoint path
   * @param {object} data - Request body data
   * @param {object} config - Additional axios config
   * @returns {Promise} Response object
   */
  async put(path, data = {}, config = {}) {
    try {
      const response = await this.client.put(path, data, config);
      return this._formatResponse(response);
    } catch (error) {
      return this._handleError(error);
    }
  }

  /**
   * DELETE request
   * @param {string} path - Endpoint path
   * @param {object} config - Additional axios config
   * @returns {Promise} Response object
   */
  async delete(path, config = {}) {
    try {
      const response = await this.client.delete(path, config);
      return this._formatResponse(response);
    } catch (error) {
      return this._handleError(error);
    }
  }

  /**
   * Format response into standardized object
   * @private
   * @param {object} response - Axios response object
   * @returns {object} Formatted response
   */
  _formatResponse(response) {
    return {
      statusCode: response.status,
      statusText: response.statusText,
      data: response.data,
      headers: response.headers,
      isSuccess: response.status >= 200 && response.status < 300,
    };
  }

  /**
   * Handle request errors
   * @private
   * @param {Error} error - Axios error object
   * @returns {object} Error response object
   */
  _handleError(error) {
    if (error.response) {
      // Request made, server responded with error status
      return {
        statusCode: error.response.status,
        statusText: error.response.statusText,
        data: error.response.data,
        headers: error.response.headers,
        isSuccess: false,
        error: error.message,
      };
    } else if (error.request) {
      // Request made but no response received
      throw new Error(`No response received: ${error.message}`);
    } else {
      // Error in request setup
      throw new Error(`Request error: ${error.message}`);
    }
  }
}

module.exports = HTTPClient;
