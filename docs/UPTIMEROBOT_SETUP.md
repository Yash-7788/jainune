# UptimeRobot Heartbeat & Keep-Alive Daemon Setup

This guide documents the setup of UptimeRobot to ensure the free Render instance (`jainune-backend-api`) runs 24/7 without being suspended by Render's 15-minute idle spin-down policy.

---

## 1. Background & Free-Tier Mechanics

- **Render Free Tier Limit**: 750 free compute hours/month (sufficient for 1 continuous web service: 24h × 31d = 744h).
- **Render Idle Spin-Down**: Free instances spin down after **15 minutes** of HTTP inactivity. Cold starts can take 45–60 seconds.
- **Heartbeat Strategy**: Pinging the zero-DB `/health` endpoint every **10 minutes** ensures the instance never experiences 15 minutes of inactivity, keeping memory warm and eliminating cold starts for real users.

---

## 2. UptimeRobot Monitor Configuration

1. Create a free account or log in at [UptimeRobot](https://uptimerobot.com/).
2. Click **+ Add New Monitor**.
3. Fill in the parameters exactly as specified:

| Parameter | Recommended Value | Notes |
| :--- | :--- | :--- |
| **Monitor Type** | `HTTP(s)` | Standard HTTP request |
| **Friendly Name** | `Jainune Render Keep-Alive` | Any descriptive name |
| **URL (or IP)** | `https://jainune-backend-api.onrender.com/health` | Replace domain if custom domain mapped |
| **Monitoring Interval** | `10 minutes` | Beats 15-min idle timeout |
| **Monitor Timeout** | `30 seconds` | Standard request timeout |
| **HTTP Method** | `GET` | |
| **SSL Verification** | `Checked` | Validates Let's Encrypt TLS certificate |

4. Under **Alert Contacts to Notify**, select your email / Slack / Discord channel to receive downtime notifications.
5. Click **Create Monitor**.

---

## 3. Endpoint Characteristics (`/health`)

- **Route**: `GET /health`
- **Response Format**:
  ```json
  {
    "status": "online",
    "service": "jainune-api",
    "version": "2.0.0"
  }
  ```
- **Execution Overhead**: Zero database queries, zero Redis commands.
- **Response Latency**: <5ms.
- **Compute Impact**: Negligible CPU and memory utilization on Render container.
