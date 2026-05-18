"""Apply handlers for the moderation dispatcher (Pack 148-followup B1).

Each module that participates in moderation registers an `apply` handler
here. When a submission is approved, `moderation_service._dispatch_apply`
calls the handler for `sub.target_module` to perform the actual write.

Handler contract:

    async def apply(db, *, sub: ModerationSubmission, user: User) -> dict | None:
        ...

The `user` argument is the moderator who clicked approve (acts as actor
for audit / ensure_company_access). Returning a dict stores it on
`sub.apply_result`. Raising propagates to `_dispatch_apply` which
records the error on `sub.apply_error` and sets `apply_status='failed'`.
"""
