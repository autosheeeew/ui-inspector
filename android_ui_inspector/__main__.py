"""
CLI entry point for android-ui-inspector.
Usage: pip install android-ui-inspector && android-ui-inspector
"""
import argparse
import sys
import webbrowser
from pathlib import Path

# Ensure backend and project root are in path (for pip install -e . and direct run)
def _ensure_path():
    pkg_dir = Path(__file__).resolve().parent
    project_root = pkg_dir.parent
    backend_dir = project_root / "backend"
    for d in (project_root, backend_dir):
        if d.exists() and str(d) not in sys.path:
            sys.path.insert(0, str(d))

_ensure_path()


def main():
    parser = argparse.ArgumentParser(
        description="Android & iOS UI Inspector - Real-time screen streaming and hierarchy inspection"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Port to run the server (default: 8000)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open browser automatically",
    )
    args = parser.parse_args()

    # Find static dir: frontend/dist (relative to project root)
    pkg_dir = Path(__file__).resolve().parent
    project_root = pkg_dir.parent
    static_dir = project_root / "frontend" / "dist"

    if not static_dir.exists() or not (static_dir / "index.html").exists():
        print("Warning: frontend/dist not found. Run 'cd frontend && npm run build' first.")
        print("Starting API-only mode (no web UI). Visit http://{}:{}/docs for API docs.".format(args.host, args.port))
        static_dir = None

    # Import and create app
    from backend.main import create_app
    app = create_app(static_dir=static_dir)

    import uvicorn

    url = "http://{}:{}".format(args.host, args.port)
    print("")
    print("Android UI Inspector")
    print("=" * 40)
    print("Server: {}".format(url))
    if static_dir:
        print("Web UI:  {} (opening in browser...)".format(url))
    else:
        print("API Docs: {}/docs".format(url))
    print("=" * 40)

    if not args.no_open and static_dir:
        webbrowser.open(url)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
