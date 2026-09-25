# UptimeRobot Heartbeat & Keep-Alive Daemon Setup

Operational guide for configuring UptimeRobot to keep the free Render service (`jainune-backend-api`) active 24/7 without idle spin-down or running out of free-tier hours.

---

## 1. Background & Free-Tier Mechanics

- **Render Free Tier Limit**: 750 free compute hours/month across the entire account.
- **24/7 Service Hours**: 1 continuous web service running 24h × 31d = **744 hours** (leaves a 6-hour buffer).
- **Render Idle Spin-Down**: Free instances suspend after **15 minutes** of HTTP inactivity; cold starts take 45–60 seconds.
- **Heartbeat Strategy**: Pinging `/livez` every **10 minutes** ensures the instance never reaches 15 minutes of inactivity, keeping memory warm with zero DB or Redis overhead.

---

## 2. UptimeRobot Monitor Configuration

1. Log in to [UptimeRobot](https://uptimerobot.com/).
2. Click **+ Add New Monitor**.
3. Configure the monitor:

| Parameter | Recommended Value | Notes |
| :--- | :--- | :--- |
| **Monitor Type** | `HTTP(s)` | Standard HTTP GET request |
| **Friendly Name** | `Jainune Render Keep-Alive` | Identifiable monitor name |
| **URL (or IP)** | `https://jainune-backend-api.onrender.com/livez` | Zero-DB, zero-Redis endpoint (<1ms) |
| **Monitoring Interval** | `10 minutes` | Prevents 15-minute idle spin-down |
| **Monitor Timeout** | `30 seconds` | Standard request timeout |
| **HTTP Method** | `GET` | |
| **SSL Verification** | `Checked` | Validates Let's Encrypt TLS certificate |

4. Under **Alert Contacts to Notify**, select email for immediate downtime alerts.
5. Click **Create Monitor**.

---

## 3. Endpoint Characteristics (`/livez`)

- **Route**: `GET /livez` (also aliased at `/v1/health/live`)
- **Response Format**:
  ```json
  {
    "status": "alive"
  }
  ```
- **Execution Overhead**: Zero database queries, zero Redis commands.
- **Response Latency**: <1ms.
- **Compute Impact**: Negligible CPU and memory utilization on Render 0.1 vCPU.

---

## 4. Render 750h Free-Tier Account Guards

> [!WARNING]
> Render calculates 750 free compute hours **per account**, not per service.

1. **Strictly 1 Service Per Account**:
   - Run ONLY `jainune-backend-api` on your free Render account.
   - Running a second service (e.g. staging API, separate background worker, celery worker) doubles consumption to 1,488h/mo, causing instance suspension around the 15th of the month.
2. **In-Process Background Workers**:
   - All background workers (`daily_compatible`, `ephemeral_reaper`, `telemetry_worker`, and cleanup maintenance) run inside the same FastAPI process via `asyncio.create_task`. Zero extra services needed.
3. **Deploy Freeze on 30th/31st of 31-Day Months**:
   - Render zero-downtime deploys run the old and new containers concurrently for 5–10 minutes.
   - On 31-day months (744 base hours), multiple deploys on the 30th or 31st can burn the remaining 6-hour margin. Avoid non-critical redeploys on day 30 and 31.
