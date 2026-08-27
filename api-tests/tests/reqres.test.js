/**
 * API Test Suite for ReqRes (https://reqres.in)
 * Core tests covering happy path and edge cases
 * 
 * Test Coverage:
 * - 2 Happy Path cases: GET single user (success), POST create user (success)
 * - 2 Negative/Edge cases: GET non-existent user (404), POST missing required field
 */

const HTTPClient = require('../utils/client');

const BASE_URL = 'https://reqres.in/api';
const API_KEY = process.env.REQRES_API_KEY || 'free_user_3HlAYBLKIFyDKC1h491e34cTl2A';
let client;

beforeAll(() => {
  // Initialize client with API key header
  const customHeaders = {
    'x-api-key': API_KEY,
  };
  client = new HTTPClient(BASE_URL, 10000, customHeaders);
});

describe('ReqRes API - Core Test Suite', () => {
  
  describe('Happy Path Tests', () => {
    
    test('should fetch single user successfully with status 200', async () => {
      const response = await client.get('/users/1');

      expect(response.statusCode).toBe(200);
      expect(response.isSuccess).toBe(true);
      expect(response.data).toHaveProperty('data');
      
      const user = response.data.data;
      expect(user).toHaveProperty('id', 1);
      expect(user).toHaveProperty('email');
      expect(user).toHaveProperty('first_name');
      expect(user).toHaveProperty('last_name');
      expect(user).toHaveProperty('avatar');
    });

    test('should create user successfully with status 201', async () => {
      const userData = {
        name: 'John Doe',
        job: 'QA Engineer',
      };

      const response = await client.post('/users', userData);

      expect(response.statusCode).toBe(201);
      expect(response.isSuccess).toBe(true);
      expect(response.data).toHaveProperty('name', userData.name);
      expect(response.data).toHaveProperty('job', userData.job);
      expect(response.data).toHaveProperty('id');
      expect(response.data).toHaveProperty('createdAt');
    });

  });

  describe('Negative/Edge Case Tests', () => {
    
    test('should return 404 when fetching non-existent user', async () => {
      const response = await client.get('/users/9999');

      expect(response.statusCode).toBe(404);
      expect(response.isSuccess).toBe(false);
    });

    test('should handle POST with missing required field (name)', async () => {
      const userData = {
        job: 'QA Engineer',
        // name field is intentionally missing
      };

      const response = await client.post('/users', userData);

      // ReqRes doesn't strictly validate, but we verify the response
      expect(response.statusCode).toBe(201);
      expect(response.data).toHaveProperty('id');
      // Name should be undefined or missing when not provided
      expect(response.data.name === undefined || response.data.name === null || response.data.name === '').toBe(true);
    });

  });

  describe('setHeader Tests', () => {

    // Demonstrates swapping a header mid-suite via setHeader() instead of
    // building a new HTTPClient. Confirmed against the live API first:
    // no x-api-key -> 401, an invalid x-api-key -> 403.
    test('should reflect an updated x-api-key on the very next request', async () => {
      // Client already has the valid key from beforeAll — sanity check first.
      const beforeChange = await client.get('/users/1');
      expect(beforeChange.statusCode).toBe(200);

      // Swap in a bad key. setHeader mutates the shared axios instance's
      // default headers, so every request after this point uses it —
      // no new client needed.
      client.setHeader('x-api-key', 'totally-invalid-key');

      const afterChange = await client.get('/users/1');
      expect(afterChange.statusCode).toBe(403);
      expect(afterChange.isSuccess).toBe(false);

      // Restore the valid key. Important: `client` is created once in
      // beforeAll and reused across every test in this file, so a header
      // left in a broken state here would leak into whichever test runs
      // next — reset it before the test ends.
      client.setHeader('x-api-key', API_KEY);

      const afterRestore = await client.get('/users/1');
      expect(afterRestore.statusCode).toBe(200);
    });

  });

});
