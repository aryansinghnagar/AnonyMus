from flask import request

def set_security_headers(response):
    """
    Flask hook to enforce browser security headers.
    
    Sets Strict-Transport-Security (HTTPS only), X-Content-Type-Options,
    X-Frame-Options, X-XSS-Protection, CSP rules, and disables route caching
    on sensitive dashboards.
    """
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '0'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    
    # Restrict loading of scripts/frames, allowing socket connection over WS/WSS
    # Also support cdnjs for qrcode.js (relay mode dependency)
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.socket.io https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "connect-src 'self' ws: wss:;"
    )
    
    # Disable caching on core views
    if request.path in ['/login', '/register', '/chat']:
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        
    return response

def setup_security_headers(app):
    """Registers security headers on Flask application."""
    app.after_request(set_security_headers)
