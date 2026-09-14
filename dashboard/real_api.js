/**
 * Real API client — SAME interface as mock_api.js by design, so
 * config.js's USE_MOCK flag is the only thing that needs to change to go
 * from mock data to the real backend. Matches docs/api_contract.md.
 */
import { BACKEND_URL } from "./config.js";

async function handleResponse(response) {
  if (!response.ok) {
    const err = new Error(`Request failed: ${response.status}`);
    err.status = response.status;
    throw err;
  }
  return response.json();
}

export const realApi = {
  async getLatestScan(deviceId) {
    const response = await fetch(`${BACKEND_URL}/devices/${encodeURIComponent(deviceId)}/latest`);
    return handleResponse(response);
  },

  async getDeviceHistory(deviceId, limit = 20) {
    const response = await fetch(`${BACKEND_URL}/devices/${encodeURIComponent(deviceId)}/scans?limit=${limit}`);
    return handleResponse(response);
  },
};
