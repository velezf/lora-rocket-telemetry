"""Flask shell for the live dashboard (Pi-only, thin).

Boring by design (D4 + constraints): the built-in threaded dev server, bound to
0.0.0.0 on a fixed port, read-only, single user on the LAN. No WSGI stack, no auth,
no DB, no websocket. The page polls /api/state; all logic is in ground.dashboard.model
(host-tested). Flask is imported lazily so this module imports without Flask on a dev
box and the ingest service degrades gracefully if Flask is absent.
"""
DASHBOARD_PORT = 8080


def create_app(view_model_fn):
    """`view_model_fn()` returns the current view-model dict (built from an immutable
    LiveState snapshot). Grabbed fresh per request — never touches the radio/log."""
    from flask import Flask, jsonify, render_template  # pyright: ignore[reportMissingImports]  # Pi-only dep

    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html", port=DASHBOARD_PORT)

    @app.route("/api/state")
    def api_state():
        return jsonify(view_model_fn())

    return app


def serve(view_model_fn, host="0.0.0.0", port=DASHBOARD_PORT):
    """Run the built-in threaded server (call from a daemon thread in the ingest)."""
    create_app(view_model_fn).run(host=host, port=port, threaded=True, use_reloader=False)
