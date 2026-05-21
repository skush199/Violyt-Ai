FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PROGRESS_BAR=off \
    PIP_RETRIES=20

WORKDIR /app

COPY pyproject.toml ./

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -c "import pathlib, tomllib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); pathlib.Path('requirements-docker.txt').write_text('\\n'.join(data['project']['dependencies']) + '\\n', encoding='utf-8')"

RUN pip install --retries 20 --default-timeout=300 --prefer-binary -r requirements-docker.txt

COPY . .

RUN pip install --retries 20 --default-timeout=300 --prefer-binary "setuptools>=68" wheel

RUN pip install --no-build-isolation --no-deps --retries 20 --default-timeout=300 --prefer-binary .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
