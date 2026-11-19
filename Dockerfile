# SignalBrief web UI as a Hugging Face Docker Space (also runs anywhere Docker does).
# Needs one secret at runtime: NRP_API_KEY. Optional: SIGNALBRIEF_UI_PASSWORD, SIGNALBRIEF_MODEL.
FROM python:3.12-slim

# Hugging Face runs Spaces as uid 1000; give that user a writable home and app folder
RUN useradd -m -u 1000 user && mkdir -p /home/user/app && chown user:user /home/user/app
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 PYTHONUTF8=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
# openai-agents pinned to the version the app was last tested with
RUN pip install --no-cache-dir --user -r requirements.txt "openai-agents==0.24.0"

# Bake ChromaDB's embedding model (~80 MB) into the image so the first run doesn't download it
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as E; E()(['warm up'])"

COPY --chown=user . .
RUN mkdir -p output memory_web

EXPOSE 7860
CMD ["python", "web_app.py", "--host", "0.0.0.0", "--port", "7860"]
