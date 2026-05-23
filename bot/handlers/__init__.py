from bot.handlers.callback import router as callback_router
from bot.handlers.commands import router as commands_router
from bot.handlers.join_request import router as join_request_router
from bot.handlers.message import router as message_router


ALL_ROUTERS = [commands_router, callback_router, join_request_router, message_router]
