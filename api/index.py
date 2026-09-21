import os
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NewCompany.settings")

try:
    from NewCompany.wsgi import application
except Exception as exc:
    startup_error = f"{exc.__class__.__name__}: {exc}"
    startup_traceback = traceback.format_exc()

    def application(environ, start_response):
        show_traceback = os.environ.get("DJANGO_STARTUP_DEBUG") in {"1", "true", "yes", "on"}
        details = startup_traceback if show_traceback else (
            "Set DJANGO_STARTUP_DEBUG=1 temporarily to include the startup traceback in this response."
        )
        body = (
            "Django failed to start on Vercel.\n\n"
            f"{startup_error}\n\n"
            f"{details}"
        ).encode("utf-8")
        start_response(
            "503 Service Unavailable",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

app = application
handler = application
