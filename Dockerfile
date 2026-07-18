FROM python:3.10-slim

WORKDIR /srv

# Install the package (and its deps from pyproject) into site-packages.
# Copying source before install keeps app/eval importable at run time.
COPY pyproject.toml ./
COPY app ./app
COPY eval ./eval
RUN pip install --no-cache-dir .

EXPOSE 8001

# The detection pipeline must score the full response, so no --reload here.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
