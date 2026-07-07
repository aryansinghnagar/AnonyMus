# RFC 0007: CSRF Protection and Session Expiry Configuration

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

Session hijackings and Cross-Site Request Forgery (CSRF) present major threats to web-based administrative panel controls and chat pages. Attackers could trick users into executing destructive actions (such as nuking databases or resetting credentials).

## 2. Goals & Non-Goals

### Goals
- Secure all state-modifying requests (`POST`, `PUT`, `DELETE`) against CSRF attacks.
- Automatically inject and extract CSRF tokens on client requests.
- Configure a strict session lifetime policy to prevent permanent session persistency.

### Non-Goals
- Requiring CSRF tokens on read-only endpoints (`GET`, `OPTIONS`).

## 3. Design Details

The system integrates `Flask-WTF` protection:
1. **CSRF Middleware:** `CSRFProtect` is initialized on both transport instances.
2. **Fetch Interceptor:** The client page `<head>` injects a fetch interceptor that scans the page DOM for a `<meta name="csrf-token">` tag and appends it as `X-CSRFToken` to all outbound state-changing AJAX requests.
3. **Session Lifetimes:** Set `PERMANENT_SESSION_LIFETIME = timedelta(hours=8)` and set `session.permanent = True` during registration/login. Cookies are configured with `HttpOnly`, `Secure`, and `SameSite=Strict`.

## 4. Security & Privacy Implications

- **SameSite Restrictions:** Enforcing `SameSite=Strict` ensures browser clients block session cookies on third-party link navigations.
- **CSRF Token Entropy:** Tokens must be dynamically generated per request using cryptographically secure random values.

## 5. Backward Compatibility

Any client scripts making API POSTs must integrate CSRF token headers to avoid HTTP 400 Bad Request responses.
