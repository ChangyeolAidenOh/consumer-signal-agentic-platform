FROM python:3.10-slim
LABEL authors="aiden"

WORKDIR /app

# Upgrade pip to handle package name normalization correctly
RUN pip install --no-cache-dir --upgrade pip

# Install CPU-only PyTorch first so sentence-transformers does not pull CUDA builds.
# torch comes from the CPU index; its dependencies resolve from PyPI.
RUN pip install --no-cache-dir torch \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Korean embedding model during build
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('jhgan/ko-sroberta-multitask')"

# Application code and pre-built ChromaDB index
COPY . .

RUN chmod +x startup.sh

CMD ["./startup.sh"]
