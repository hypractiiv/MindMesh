# Run MindMesh

```bash
# 1. Clone the repository and navigate into the directory
git clone https://github.com/hypractiiv/agentathon-mindmesh.git
cd agentathon-mindmesh

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
export GEMINI_API_KEY="your_gemini_api_key_here"
export OPENROUTER_API_KEY="your_openrouter_api_key_here"
export DATABASE_URL="your_database_url_here"

# 4. Launch the interactive demo
streamlit run app.py
```

Open your browser at:
**http://localhost:8501**

*(For headless or terminal-only environments, run the automated 8-beat judge demo: `python cli.py --demo`)*
