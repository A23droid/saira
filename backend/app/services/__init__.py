# # Services package
# # auth_service imports user_service via `from app.services import user_service`
# # so we must NOT import auth_service here (circular import).
# # All other endpoints import their services directly.

# # from app.services.user_service import user_service

# # __all__ = ["user_service"]


# from app.services.avatar_service import avatar_service
# from app.services.oauth_service import oauth_service
# from app.services.user_service import user_service
# from app.services.project_service import project_service
# from app.services.paper_service import paper_service

# __all__ = [
#     "avatar_service",
#     "oauth_service",
#     "user_service",
#     "project_service",
#     "paper_service",
# ]