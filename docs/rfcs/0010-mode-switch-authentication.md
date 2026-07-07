# RFC 0010: Mode-Switch Endpoint Authentication and Validation

- **Status:** Approved
- **Author(s):** AnonyMus core team
- **Created:** 2026-07-03
- **Updated:** 2026-07-03

---

## 1. Context

The `/api/mode` WSGI endpoint allows switching the application's runtime transport state between P2P and Relay modes. If this endpoint remains unauthenticated, any network or malicious client actor could switch the server mode, causing denial of service or network metadata leakage.

## 2. Goals & Non-Goals

### Goals
- Secure the mode switching API endpoint against unauthorized accesses.
- Restrict endpoint execution strictly to the loopback interface (`127.0.0.1` and `[::1]`) by default.
- Support administrative secret verification when accessed remotely.

### Non-Goals
- Restricting other public APIs (like message delivery endpoints) to loopback.

## 3. Design Details

The system configures security filters on the mode routing endpoint in `server.py`:
1. **Loopback Filter:** The handler checks `request.remote_addr`. If it does not belong to the loopback set (`127.0.0.1`, `::1`, `[::1]`), access is denied unless an authorization secret matches.
2. **Secret Key Verification:** If the environment variable `ANONYMUS_ADMIN_SECRET` is set, the endpoint validates the incoming request header `X-Admin-Secret` against the secret value.
3. **Graceful Failures:** Failures return HTTP 403 Forbidden without disclosing internal registration stats.

## 4. Security & Privacy Implications

- **Privilege Escalation Mitigation:** Prevents remote attackers from shutting down peer-to-peer hidden services or forcing the system to switch to a centralized relay.
- **Audit Trails:** Swapping operations trigger secure warning logs on the local server console.

## 5. Backward Compatibility

Any external diagnostic or launcher controllers must supply loopback requests or include `X-Admin-Secret` headers to authorize mode switches.
