# Fully-qualified image name: Podman/Buildah have no implicit Docker Hub default,
# so an unqualified `python:...` either prompts for a registry or fails outright.
FROM docker.io/library/python:3.14-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["vacancy-radar", "serve", "--host", "0.0.0.0"]
