from bot.handlers.callback import router as callback_router
from bot.handlers.commands import router as commands_router
from bot.handlers.join_request import router as join_request_router
from bot.handlers.message import router as message_router
from bot.handlers.private_panel import router as private_panel_router


ALL_ROUTERS = [private_panel_router, commands_router, callback_router, join_request_router, message_router]
