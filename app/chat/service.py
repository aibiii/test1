from pydantic import BaseSettings

from .adapters.chat_service import ChatService
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file


class Config(BaseSettings):
    HERE_API_KEY: str


class Service:
    def __init__(self, api_key: str):
        self.chat_service = ChatService(api_key)


def get_service():
    token = os.getenv("OPEN_API_KEY")
    return Service(token)