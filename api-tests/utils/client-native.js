/**
 * HTTP Client for API Testing — built on Node's core http/https modules only.
 * Same public interface as client.js (get/post/put/delete, same response shape)
 * so the two can be swapped in reqres.test.js to compare line-for-line what
 * Axios is doing for you under the hood.
 */

const http = require('http');
const https = require('https');
const { URL } = require('url');

class HTTPClient {
  /**
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
  }

  setHeader(key, value) {
    this.headers[key] = value;
  }

  async get(path, config = {}) {
    return this._request('GET', path, undefined, config);
  }

  async post(path, data = {}, config = {}) {
    return this._request('POST', path, data, config);
  }

  async put(path, data = {}, config = {}) {
    return this._request('PUT', path, data, config);
  }

  async delete(path, config = {}) {
    return this._request('DELETE', path, undefined, config);
  }

  /**
   * Core request implementation. Axios does all of this for you:
   * base URL joining, JSON stringify/parse, timeout handling, and
   * treating non-2xx status codes as errors.
   * @private
   */
  _request(method, path, data, config = {}) {
    return new Promise((resolve, reject) => {
      const url = new URL(path, this.baseURL);
      const isHttps = url.protocol === 'https:';
      const transport = isHttps ? https : http;

      const headers = { ...this.headers, ...(config.headers || {}) };
      let body;
      if (data !== undefined) {
        body = JSON.stringify(data);
        headers['Content-Length'] = Buffer.byteLength(body);
      }

      const requestOptions = {
        method,
        headers,
        timeout: this.timeout,
      };

      const req = transport.request(url, requestOptions, (res) => {
        const chunks = [];

        res.on('data', (chunk) => chunks.push(chunk));

        res.on('end', () => {
          const rawBody = Buffer.concat(chunks).toString('utf8');
          let parsedBody = rawBody;
          try {
            parsedBody = rawBody ? JSON.parse(rawBody) : undefined;
          } catch {
            // Response wasn't JSON — return the raw text, same as Axios would
            // for a non-JSON content type.
          }

          resolve(this._formatResponse(res, parsedBody));
        });
      });

      // Axios rejects automatically on network errors; with core http/https
      // you have to wire this up yourself.
      req.on('error', (error) => {
        reject(new Error(`Request error: ${error.message}`));
      });

      // Axios's `timeout` option does this internally too — without it,
      // a hung connection would wait forever.
      req.on('timeout', () => {
        req.destroy();
        reject(new Error(`No response received: timeout of ${this.timeout}ms exceeded`));
      });

      if (body !== undefined) {
        req.write(body);
      }

      req.end();
    });
  }

  /**
   * Format response into the same standardized shape as client.js,
   * including turning non-2xx codes into isSuccess: false instead of
   * throwing — Axios throws on non-2xx by default, so this mimics the
   * try/catch handling client.js does in _handleError.
   * @private
   */
  _formatResponse(res, data) {
    return {
      statusCode: res.statusCode,
      statusText: res.statusMessage,
      data,
      headers: res.headers,
      isSuccess: res.statusCode >= 200 && res.statusCode < 300,
    };
  }
}

module.exports = HTTPClient;
