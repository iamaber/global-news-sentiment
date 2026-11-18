import argparse
import sys

import uvicorn

DEFAULT_HOST = "127.0.0.1"
PORT = 8501
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def main():
    parser = argparse.ArgumentParser(description="Real-time News Sentiment Analysis")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=(
            "Interface to bind (default: 127.0.0.1). Use 0.0.0.0 only when you "
            "intend to expose the unauthenticated API and dashboard."
        ),
    )
    args = parser.parse_args()

    if args.host not in LOOPBACK_HOSTS:
        print(
            f"Warning: binding to {args.host} exposes the API and dashboard "
            "beyond this machine. The API has no authentication.",
            file=sys.stderr,
        )

    uvicorn.run("backend.api:app", host=args.host, port=PORT)


if __name__ == "__main__":
    main()
