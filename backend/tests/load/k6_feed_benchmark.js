import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

// Custom metrics
const feedDuration = new Trend('feed_response_time_ms');
const errorRate = new Rate('feed_error_rate');

export const options = {
  stages: [
    { duration: '30s', target: 20 },  // Ramp-up
    { duration: '1m',  target: 100 }, // Sustained heavy load
    { duration: '2m',  target: 100 }, // Hold load
    { duration: '30s', target: 0 },   // Ramp-down
  ],
  thresholds: {
    // 95% of discovery requests must finish under 30ms (BRRE p95 target)
    http_req_duration: ['p(95)<30', 'p(99)<60'],
    // Error rate must stay below 1%
    http_req_failed: ['rate<0.01'],
    feed_error_rate: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.AUTH_TOKEN || 'test-jwt-token';

const headers = {
  'Authorization': `Bearer ${TOKEN}`,
  'Content-Type': 'application/json',
};

export default function () {
  // 1. Fetch Discovery Feed batch
  const feedRes = http.get(`${BASE_URL}/v1/feed?limit=15`, { headers });
  const isFeedOk = check(feedRes, {
    'feed status is 200': (r) => r.status === 200,
    'feed returns candidates': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body.candidates);
      } catch (_) {
        return false;
      }
    },
  });

  feedDuration.add(feedRes.timings.duration);
  errorRate.add(!isFeedOk);

  // Think time between swipes (100ms - 500ms)
  sleep(Math.random() * 0.4 + 0.1);

  // 2. Fetch Daily Compatible profile (1 in 5 iterations)
  if (Math.random() < 0.2) {
    const dailyRes = http.get(`${BASE_URL}/v1/feed/daily-compatible`, { headers });
    check(dailyRes, {
      'daily compatible status is 200': (r) => r.status === 200,
      'has locking mechanism': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.locked_until !== undefined;
        } catch (_) {
          return false;
        }
      },
    });
    sleep(0.5);
  }
}
