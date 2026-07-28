// Backend always runs on port 8002; derive the host from wherever the app was loaded
// so the API is reachable from any machine on the network, not just localhost.
export const API_ROOT = `${window.location.protocol}//${window.location.hostname}:8002/api/`;
