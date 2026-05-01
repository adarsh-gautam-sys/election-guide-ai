import os
import google.auth
from google import genai
os.environ['GOOGLE_CLOUD_PROJECT'] = 'electionguide-ai-7c996'
os.environ['GEMINI_API_KEY'] = 'test_key'

# simulate run_async context
original_project = os.environ.get('GOOGLE_CLOUD_PROJECT')
del os.environ['GOOGLE_CLOUD_PROJECT']
try:
    client = genai.Client()
    print('Has API Key:', bool(client._api_client.api_key))
    print('Has Credentials:', hasattr(client._api_client, 'credentials') and bool(client._api_client.credentials))
finally:
    if original_project is not None:
        os.environ['GOOGLE_CLOUD_PROJECT'] = original_project
