import os
import google.auth
from google import genai
os.environ['GEMINI_API_KEY'] = 'test_key'
if 'GOOGLE_CLOUD_PROJECT' in os.environ:
    del os.environ['GOOGLE_CLOUD_PROJECT']
client = genai.Client()
print('API Key:', client._api_client.api_key)
print('Vertex AI:', client._api_client.vertexai)
