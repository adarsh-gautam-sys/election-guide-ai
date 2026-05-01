import os
import google.auth
from google import genai
os.environ['GOOGLE_CLOUD_PROJECT'] = 'electionguide-ai-7c996'
os.environ['GEMINI_API_KEY'] = 'test_key'
client = genai.Client()
print('API Key:', client._api_client.api_key)
print('Vertex AI:', client._api_client.vertexai)
