#!/usr/bin/env python3
"""all-MiniLM-L6-v2 sentence embeddings as a JSON-lines service (one request per line: {"texts": [...]} -> {"vectors": [...]}).

Runs in the Python 3.12 environment that has sentence-transformers (results/ext/venv-gmem); the RelBench harness uses
it for AgentSM's trajectory retrieval and schema-linking vector search (MiniLM-L6-v2, as AgentSM §4.1). Vectors are
L2-normalised, so the harness ranks by inner product, which is what a FAISS flat inner-product index computes.
"""
import json
import os
import sys


def main():
    out = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    sys.stdout = sys.stderr
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    out.write(json.dumps({"ready": True}) + "\n")
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        vecs = model.encode(req["texts"], normalize_embeddings=True, show_progress_bar=False)
        out.write(json.dumps({"vectors": [v.tolist() for v in vecs]}) + "\n")


if __name__ == "__main__":
    main()
