import os
from dotenv import load_dotenv

load_dotenv()

def get_env(name, default=None):
    return os.getenv(name, default)
