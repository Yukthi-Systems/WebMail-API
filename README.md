# WebMail-API

WebMail Main API — the backend that powers WebMail's email features.

## What this is

This API handles the core webmail functionality — things like connecting to mail servers over IMAP and managing email data for the platform.

## Built with

- Python 3.12
- FastAPI
- PostgreSQL (using asyncpg)
- IMAPClient for email access
- Gunicorn to run the app
- Docker for easy deployment

## Getting started

You'll need Python 3.12 installed. Docker is optional if you'd rather run it in a container.

Clone the repo and install the dependencies:

```bash
git clone https://github.com/Yukthi-Systems/WebMail-API.git
cd WebMail-API
pip install -r requirements.txt
```

Or run it with Docker:

```bash
docker build -t webmail-api .
docker run -p 8086:8086 webmail-api
```

## License

This project uses the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for the full text.

## Contributing

Found a bug or want to add something? Open an issue or send a pull request — contributions are welcome.
