from pydantic import BaseModel


class ClientMessage(BaseModel):
    chat_id: int
    username: str
    phone_number: str
    source: str
    user_message: str
    ai_response: str
    resume_url: str


class NotificationMessage(BaseModel):
    chat_id: int
    notification_message: str
