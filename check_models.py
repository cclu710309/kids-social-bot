import os
import urllib.request
import json
import streamlit as st

api_key = os.environ.get("GEMINI_API_KEY", "")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
try:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode("utf-8"))
        models = data.get("models", [])
        for m in models:
            name = m.get("name")
            supported_methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in supported_methods:
                print(f"Model: {name}")
except Exception as e:
    print(f"Error: {e}")
